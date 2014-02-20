'''Get Viddler Flash Video URL

For more info, please see:

* http://archiveteam.org/index.php?title=Viddler
* https://github.com/chfoo/bearded-octo-nemesis/blob/master/gatekeeper-fdf8c6995db46b9e079351a7ed9bda66.swf.as
* https://code.google.com/p/mp-onlinevideos2/source/browse/trunk/SiteUtilProjects/OnlineVideos.Sites.doskabouter/Hoster/Viddler.cs
'''
from __future__ import print_function

from Crypto.Cipher import Blowfish
import argparse
import io
import urllib2

import pyamf.remoting

USER_AGENT = 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/32.0.1700.76 Safari/537.36'

def main():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('video_id')
    arg_parser.add_argument('--wget', action='store_true')
    args = arg_parser.parse_args()

    request_payload = video_info_request(args.video_id)
    response_payload = make_info_request(request_payload)
    envelope = read_response_payload(response_payload)
    paths = list(process_envelope(envelope))

    for path in paths:
        print(path)


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

        yield decrypt_path(path)


def decrypt_path(path):
    path = path.decode('hex')
    cipher_key = b'kluczyk'
    initialization_vector = b'\x00' * 8
    cipher = Blowfish.new(cipher_key, Blowfish.MODE_CFB, initialization_vector,
        segment_size=64)

    padding = b'\x00' * (len(path) % 64)
    ciphertext = path + padding
    plaintext = cipher.decrypt(ciphertext)
    plaintext = plaintext[:len(path)]

    return plaintext

if __name__ == '__main__':
    main()

