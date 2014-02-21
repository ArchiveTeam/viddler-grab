import datetime
from distutils.version import StrictVersion
import glob
import hashlib
import json
import os
import re
import seesaw
from seesaw.config import NumberConfigValue, realize
from seesaw.externalprocess import WgetDownload, RsyncUpload, CurlUpload
from seesaw.item import ItemInterpolation, ItemValue
from seesaw.pipeline import Pipeline
from seesaw.project import Project
from seesaw.task import SimpleTask, LimitConcurrent
from seesaw.tracker import (GetItemFromTracker, SendDoneToTracker,
    PrepareStatsForTracker, UploadWithTracker)
from seesaw.util import find_executable
import shutil
import socket
import sys
import time


# check the seesaw version
if StrictVersion(seesaw.__version__) < StrictVersion("0.1.5"):
    raise Exception("This pipeline needs seesaw version 0.1.5 or higher.")


###########################################################################
# Find a useful Wget+Lua executable.
#
# WGET_LUA will be set to the first path that
# 1. does not crash with --version, and
# 2. prints the required version string
WGET_LUA = find_executable(
    "Wget+Lua",
    ["GNU Wget 1.14.lua.20130523-9a5c"],
    [
        "./wget-lua",
        "./wget-lua-warrior",
        "./wget-lua-local",
        "../wget-lua",
        "../../wget-lua",
        "/home/warrior/wget-lua",
        "/usr/bin/wget-lua"
    ]
)

if not WGET_LUA:
    raise Exception("No usable Wget+Lua found.")


def check_imports():
    import pyamf.remoting
    from Crypto.Cipher import Blowfish


check_imports()


###########################################################################
# The version number of this pipeline definition.
#
# Update this each time you make a non-cosmetic change.
# It will be added to the WARC files and reported to the tracker.
VERSION = "20140221.02"
USER_AGENT = 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/31.0.1650.57 Safari/537.36'
TRACKER_ID = 'viddler'
TRACKER_HOST = 'tracker.archiveteam.org'


###########################################################################
# This section defines project-specific tasks.
#
# Simple tasks (tasks that do not need any concurrency) are based on the
# SimpleTask class and have a process(item) method that is called for
# each item.
class CheckIP(SimpleTask):
    def __init__(self, warc_prefix):
        SimpleTask.__init__(self, "CheckIP")
        self._counter = 0

    def process(self, item):
        # NEW for 2014! Check if we are behind firewall/proxy
        ip_str = socket.gethostbyname('www.viddler.com')
        if ip_str not in ('75.98.67.106', '75.98.67.105'):
            item.log_output('Got IP address: %s' % ip_str)
            item.log_output(
                'Are you behind a firewall/proxy? That is a big no-no!')
            raise Exception(
                'Are you behind a firewall/proxy? That is a big no-no!')

        # Check only occasionally
        if self._counter <= 0:
            self._counter = 10
        else:
            self._counter -= 1


class PrepareDirectories(SimpleTask):
    def __init__(self, warc_prefix):
        SimpleTask.__init__(self, "PrepareDirectories")
        self.warc_prefix = warc_prefix

    def process(self, item):
        item_name = item["item_name"]
        dirname = "/".join((item["data_dir"], item_name))

        if os.path.isdir(dirname):
            shutil.rmtree(dirname)

        os.makedirs(dirname)

        item["item_dir"] = dirname
        item["warc_file_base"] = "%s-%s-%s" % (self.warc_prefix, item_name,
            time.strftime("%Y%m%d-%H%M%S"))

        open("%(item_dir)s/%(warc_file_base)s.warc.gz" % item, "w").close()


class MoveFiles(SimpleTask):
    def __init__(self):
        SimpleTask.__init__(self, "MoveFiles")

    def process(self, item):
        # NEW for 2014! Check if wget was compiled with zlib support
        if os.path.exists("%(item_dir)s/%(warc_file_base)s.warc"):
            raise Exception('Please compile wget with zlib support!')

        os.rename("%(item_dir)s/%(warc_file_base)s.warc.gz" % item,
              "%(data_dir)s/%(warc_file_base)s.warc.gz" % item)

        files_to_upload = ["%(data_dir)s/%(warc_file_base)s.warc.gz" % item]

        extra_filenames = self.find_extra_files(item)

        for extra_filename in extra_filenames:
            dirname, filename = os.path.split(extra_filename)
            new_path = os.path.join("%(data_dir)s" % item, filename)

            os.rename(extra_filename, new_path)
            files_to_upload.append(new_path)

        item['files_to_upload'] = files_to_upload

        shutil.rmtree("%(item_dir)s" % item)

    def find_extra_files(self, item):
        return glob.glob("%(item_dir)s/viddler_amf.*.warc.gz" % item)


def get_hash(filename):
    with open(filename, 'rb') as in_file:
        return hashlib.sha1(in_file.read()).hexdigest()


CWD = os.getcwd()
PIPELINE_SHA1 = get_hash(os.path.join(CWD, 'pipeline.py'))
LUA_SHA1 = get_hash(os.path.join(CWD, 'viddler.lua'))


def stats_id_function(item):
    # NEW for 2014! Some accountability hashes and stats.
    return {
        'pipeline_hash': PIPELINE_SHA1,
        'lua_hash': LUA_SHA1,
        'python_version': sys.version,
    }


class CustomUploadWithTracker(UploadWithTracker):
    def process_body(self, body, item):
        data = json.loads(body)
        if "upload_target" in data:
            inner_task = None

            if re.match(r"^rsync://", data["upload_target"]):
                item.log_output("Uploading with Rsync to %s" % data["upload_target"])
                inner_task = RsyncUpload(data["upload_target"], realize(self.files, item), target_source_path=self.rsync_target_source_path, bwlimit=self.rsync_bwlimit, extra_args=self.rsync_extra_args, max_tries=1)

            elif re.match(r"^https?://", data["upload_target"]):
                item.log_output("Uploading with Curl to %s" % data["upload_target"])

                if len(self.files) != 1:
                    item.log_output("Curl expects to upload a single file.")
                    self.fail_item(item)
                    return

                inner_task = CurlUpload(data["upload_target"], self.files[0], self.curl_connect_timeout, self.curl_speed_limit, self.curl_speed_time, max_tries=1)

            else:
                item.log_output("Received invalid upload type.")
                self.fail_item(item)
                return

            inner_task.on_complete_item += self._inner_task_complete_item
            inner_task.on_fail_item += self._inner_task_fail_item
            inner_task.enqueue(item)

        else:
            item.log_output("Tracker did not provide an upload target.")
            self.schedule_retry(item)


class CustomPrepareStatsForTracker(PrepareStatsForTracker):
    def process(self, item):
        total_bytes = {}
        for (group, files) in self.file_groups.iteritems():
            total_bytes[group] = sum([os.path.getsize(realize(f, item)) for f in realize(files, item)])

        stats = {}
        stats.update(self.defaults)
        stats["item"] = item["item_name"]
        stats["bytes"] = total_bytes

        if self.id_function:
            stats["id"] = self.id_function(item)

        item["stats"] = realize(stats, item)


class WgetArgs(object):
    def realize(self, item):
        wget_args = [
            WGET_LUA,
            "-U", "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/32.0.1700.76 Safari/537.36",
            "-nv",
            "-o", ItemInterpolation("%(item_dir)s/wget.log"),
            "--lua-script", "viddler.lua",
            "--no-check-certificate",
            "--output-document", ItemInterpolation("%(item_dir)s/wget.tmp"),
            "--truncate-output",
            "-e", "robots=off",
            "--no-cookies",
            "--rotate-dns",
            # "--recursive", "--level=inf",
            "--page-requisites",
            "--timeout", "60",
            "--tries", "inf",
            "--span-hosts",
            "--no-parent",
            "--waitretry", "3600",
            "--domains", "viddler.com",
            "--warc-file",
                ItemInterpolation("%(item_dir)s/%(warc_file_base)s"),
            "--warc-header", "operator: Archive Team",
            "--warc-header", "viddler-dld-script-version: " + VERSION,
            "--warc-header", ItemInterpolation("viddler-user: %(item_name)s"),
        ]

        item_name = item['item_name']
        start, end = item_name.split(':', 1)
        start = int(start)
        end = int(end)

        assert start <= end

        for video_id_num in range(start, end + 1):
            # Note: it appears viddler doesn't use leading 0 padding so
            # don't include it
            video_id_str = '{0:x}'.format(video_id_num)

            wget_args.append('http://www.viddler.com/v/%s' % video_id_str)

        if 'bind_address' in globals():
            wget_args.extend(['--bind-address', globals()['bind_address']])
            print('')
            print('*** Wget will bind address at {0} ***'.format(
                globals()['bind_address']))
            print('')

        return realize(wget_args, item)


downloader = globals()['downloader']  # quiet the code checker

###########################################################################
# Initialize the project.
#
# This will be shown in the warrior management panel. The logo should not
# be too big. The deadline is optional.
project = Project(
    title="Viddler",
    project_html="""
    <img class="project-logo" alt="" src="http://archiveteam.org/images/a/aa/ViddlerLogoLg.png" height="50" />
    <h2>Viddler <span class="links">
        <a href="http://www.viddler.com/">Website</a> &middot;
        <a href="http://%s/%s/">Leaderboard</a></span></h2>
    <p><b>Viddler</b>: It's time to pay the fiddler.</p>
    """ % (TRACKER_HOST, TRACKER_ID)
    ,
    utc_deadline=datetime.datetime(year=2014, month=3, day=11)
)

pipeline = Pipeline(
    GetItemFromTracker("http://%s/%s" % (TRACKER_HOST, TRACKER_ID), downloader,
        VERSION),
    PrepareDirectories(warc_prefix="viddler"),
    WgetDownload(
        WgetArgs(),
        max_tries=5,
        accept_on_exit_code=[0, 8],
        env={
            'item_name': ItemValue("item_name"),
            'item_dir': ItemValue("item_dir"),
        }
    ),
    MoveFiles(),
    CustomPrepareStatsForTracker(
        defaults={"downloader": downloader, "version": VERSION},
        file_groups={
            "data": ItemValue("files_to_upload")
        },
        id_function=stats_id_function,
    ),
    LimitConcurrent(NumberConfigValue(min=1, max=4, default="1",
        name="shared:rsync_threads", title="Rsync threads",
        description="The maximum number of concurrent uploads."),
        CustomUploadWithTracker(
            "http://%s/%s" % (TRACKER_HOST, TRACKER_ID),
            downloader=downloader,
            version=VERSION,
            files=ItemValue("files_to_upload"),
            rsync_target_source_path=ItemInterpolation("%(data_dir)s/"),
            rsync_extra_args=[
                "--recursive",
                "--partial",
                "--partial-dir", ".rsync-tmp"
            ]
            ),
    ),
    SendDoneToTracker(
        tracker_url="http://%s/%s" % (TRACKER_HOST, TRACKER_ID),
        stats=ItemValue("stats")
    )
)
