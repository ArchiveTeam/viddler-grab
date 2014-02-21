#!/usr/bin/env python
'''Get Viddler Flash Video URL

For more info, please see:

* http://archiveteam.org/index.php?title=Viddler
* https://github.com/chfoo/bearded-octo-nemesis/blob/master/gatekeeper-fdf8c6995db46b9e079351a7ed9bda66.swf.as
* https://code.google.com/p/mp-onlinevideos2/source/browse/trunk/SiteUtilProjects/OnlineVideos.Sites.doskabouter/Hoster/Viddler.cs
'''
from __future__ import print_function

from Crypto.Cipher import Blowfish
import argparse
import json
import os.path
import subprocess
import sys
import tempfile
import time
import urllib2
import urlparse

import pyamf.remoting


VERSION = '20140220.01'
USER_AGENT = 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/32.0.1700.76 Safari/537.36'


def main():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('video_id')
    arg_parser.add_argument('--wget', action='store_true')
    args = arg_parser.parse_args()

    print('% RiDDLeR v1.0 ViDDLeR DeCRYPToR %', file=sys.stderr)

    print('% Request riddle..', file=sys.stderr)
    request_payload = video_info_request(args.video_id)

    print('% Cracking riddle..', file=sys.stderr)
    response_payload = make_info_request(request_payload)
    envelope = read_response_payload(response_payload)
    paths = list(process_envelope(envelope))

    print('% Cracked', len(paths), 'URLs!', file=sys.stderr)

    for path in paths:
        print(path)

    if args.wget:
        print('% Recording WARC..', file=sys.stderr)
        item_dir = os.environ['item_dir']
        run_wget(args.video_id, request_payload, item_dir, paths)

    print('% Done.', file=sys.stderr)


def video_info_request(video_id):
    req = pyamf.remoting.Request(
        'viddlerGateway.getVideoInfo',
        [video_id, None, None, "false"])
    envelope = pyamf.remoting.Envelope(amfVersion=0)
    envelope.bodies.append(('/1', req))
    stream = pyamf.remoting.encode(envelope)

    return stream.read()


def make_info_request(payload):
    headers = {
        'Content-Type': 'application/x-amf',
        'User-Agent': USER_AGENT,
    }
    request = urllib2.Request('http://www.viddler.com/amfgateway.action',
        headers=headers, data=payload)
    response = urllib2.urlopen(request)

    return response.read()


def read_response_payload(payload):
    return pyamf.remoting.decode(payload)


def process_envelope(envelope):
    key, response = envelope.bodies[0]

    video_info = response.body
    version = video_info['version']
    if version != 2:
        raise Exception('Unable to handle version {0}.'.format(version))

    for file_info in video_info['files']:
        path = file_info['path']
        decrypted_path = decrypt_path(path)
        host = urlparse.urlsplit(decrypted_path).hostname
        url = decrypted_path + '?' + get_edgecast_token(host)

        yield url


def decrypt_path(path):
    path = path.decode('hex')
    cipher_key = b'kluczyk'
    initialization_vector = b'\x00' * 8
    cipher = Blowfish.new(cipher_key, Blowfish.MODE_CFB, initialization_vector,
        segment_size=64)

    padding = b'\x00' * (64 - (len(path) % 64))
    ciphertext = path + padding
    plaintext = cipher.decrypt(ciphertext)
    plaintext = plaintext[:len(path)]

    return plaintext


def get_edgecast_token(host=None):
    k = b'46377904c6c8'
    valid_time = int(time.time() + 5 * 60)
    s = 'ec_expire=' + str(valid_time)

    if host:
        s += '&ec_host_allow=' + host

    return ec_encrypt(k, s)


def ec_encrypt(key, text):
    text = text.replace('ec_secure=1', '')
    text = 'ec_secure=' + pad_left(str(len(text) + 14), "0", 3) + '&' + text

    initialization_vector = b'\x00' * 8
    cipher = Blowfish.new(key, Blowfish.MODE_CFB, initialization_vector,
        segment_size=64)

    padding = '\x00' * (64 - (len(text) % 64))
    plaintext = text + padding
    ciphertext = cipher.encrypt(plaintext)[:len(text)].encode('hex')

    return ciphertext


def pad_left(text, character, length):
    while len(text) < length:
        text = character + text
    return text


# Code below taken from seesaw.util
def test_executable(name, version, path, version_arg="-V"):
    '''Try to run an executable and check its version.'''
#     print "Looking for %s in %s" % (name, path)
    try:
        process = subprocess.Popen(
            [path, version_arg],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout_data, stderr_data = process.communicate()
        result = stdout_data + stderr_data
        if not process.returncode == 0:
#             print "%s: Returned code %d" % (path, process.returncode)
            return False

        if isinstance(version, basestring):
            if not version in result:
#                 print "%s: Incorrect %s version (want %s)." % (path, name, version)
                return False
        elif hasattr(version, "search"):
            if not version.search(result):
#                 print "%s: Incorrect %s version." % (path, name)
                return False
        elif hasattr(version, "__iter__"):
            if not any((v in result) for v in version):
#                 print "%s: Incorrect %s version (want %s)." % (path, name, str(version))
                return False

#         print "Found usable %s in %s" % (name, path)
        return True
    except OSError as e:
#         print "%s:" % path, e
        return False


def find_executable(name, version, paths, version_arg="-V"):
    '''Returns the path of a matching executable.

    .. seealso:: :func:`test_executable`
    '''
    for path in paths:
        if test_executable(name, version, path, version_arg):
            return path
    return None

# Code above taken from seesaw.util

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


def run_wget(video_id, payload, item_dir, decrypted_urls):
    decrypted_urls_str = json.dumps(decrypted_urls)

    if not WGET_LUA:
        raise Exception('Wget+Lua not found')

    with tempfile.NamedTemporaryFile() as payload_temp_file:
        payload_temp_file.write(payload)
        payload_temp_file.flush()

        wget_args = [
            WGET_LUA,
            "-U", USER_AGENT,
            "-nv",
            "-o", os.path.join(
                item_dir, "wget_amf_{0}.log".format(video_id)
            ),
            "--no-check-certificate",
            "--output-document", os.path.join(
                item_dir, "wget_amf_{0}.tmp".format(video_id)
            ),
            "--truncate-output",
            "-e", "robots=off",
            "--no-cookies",
            "--rotate-dns",
            "--timeout", "60",
            "--tries", "10",
            "--waitretry", "3600",
            "--warc-file", os.path.join(
                item_dir, "viddler_amf.{0}.{1}".format(video_id, int(time.time()))
            ),
            "--warc-header", "operator: Archive Team",
            "--warc-header", "viddler-riddler-dld-script-version: " + VERSION,
            "--warc-header", "viddler-video-id: {0}".format(video_id),
            "--warc-header", "viddler-video-resolved-urls-json: {0}".format(
                decrypted_urls_str),
            '--method', 'POST',
            '--body-file', payload_temp_file.name,
            '--header', 'Content-Type: application/x-amf',
            'http://www.viddler.com/amfgateway.action'
        ]

        subprocess.call(wget_args)

if __name__ == '__main__':
    main()
