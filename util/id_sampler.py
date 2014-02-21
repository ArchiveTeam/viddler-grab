'''This script samples videos IDs to find the percentage of 200 OK and
404 Not found'''
from __future__ import print_function
import random
import urllib2

URL = 'http://www.viddler.com/v/{0:x}'


def main(start=0, end=2 ** 32 - 1):
    random.seed(12345)

    ok = 0
    bad = 0

    for video_id in random.sample(xrange(start, end + 1), 1000):
        try:
            url = URL.format(video_id)
            urllib2.urlopen(url)
        except urllib2.URLError as error:
            print(error)
            bad += 1
        else:
            ok += 1

        ratio = float(ok) / bad
        print('ID=', video_id, '{0:x}'.format(video_id), 'OK=', ok, 'Bad=', bad, 'Ratio=', ratio)

if __name__ == '__main__':
    main()
