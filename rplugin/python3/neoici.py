#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pynvim

import sys
import os
import pickle
import json
import requests
import xmltodict
from pydub import AudioSegment
from pydub.playback import play
from validators import url as valid_url
import io
import threading

class ResultThread(threading.Thread):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.daemon = False
        self._result = None

    def run(self):
        try:
            if self._target:
                self._result = self._target(*self._args, **self._kwargs)
        finally:
            del self._target, self._args, self._kwargs

    def join(self, timeout=None):
        super().join(timeout)
        return self._result

    def start(self):
        super().start()
        return self

    @property
    def result(self):
        return self._result


class URLFetcher(ResultThread):
    def __init__(self, url: str, params: dict = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._url = url
        self._params = params
        self._target = self._fetcher

    def _valid(self):
        try:
            return valid_url(self._url)
        except Exception:
            return False


    def _fetcher(self):
        try:
            if not self._valid():
                return None

            res = requests.get(url=self._url, params=self._params)
            if res.status_code != 200:
                return None

            return self._parser(res.content)
        except Exception:
            return None

    def _parser(self, content: bytes):
        return content


class MP3Fetcher(URLFetcher):
    def __init__(self, url: str, *args, **kwargs):
        super().__init__(url=url, params=None, *args, **kwargs)

    def _valid(self):
        return super()._valid() and self._url.endswith('mp3')

class LDBPusher(threading.Thread):
    _URL = 'http://localhost:5432'

    def __init__(self, word: str, data: dict = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.daemon = True
        self._word = word
        self._data = data
        self._target = self._pusher

    def _pusher(self):
        if self._data is None:
            requests.delete(url=self._URL, params={'word': self._word})
        else:
            requests.put(url=self._URL, params={'word': self._word}, data=pickle.dumps(self._data, protocol=-1))



class LDBFetcher(URLFetcher):
    _URL = 'http://localhost:5432'

    def __init__(self, word: str, *args, **kwargs):
        super().__init__(url=self._URL, params={'word': word}, *args, **kwargs)

    def _parser(self, content: bytes) -> dict:
        return pickle.loads(content)


class ICIFetcher(URLFetcher):
    _KEY = 'E0F0D336AF47D3797C68372A869BDBC5'
    _URL = 'http://dict-co.iciba.com/api/dictionary.php'

    def __init__(self, word: str, t: str = 'json', *args, **kwargs):
        super().__init__(
            url=self._URL,
            params={
                'key': self._KEY,
                'type': t,
                'w': word
            },
            *args,
            **kwargs)

def _is_valid_url(url):
    return isinstance(url, str) and url.endswith('mp3') and valid_url(url)

class JSONICIFetcher(ICIFetcher):
    def __init__(self, word: str, *args, **kwargs):
        super().__init__(word=word, t='json', *args, **kwargs)


    @staticmethod
    def _mp3_fetcher(url):
        if not_is_valid_url(url):
            return None
        t = MP3Fetcher(url=url)
        t.start()
        return t

    def _parser(self, content: bytes) -> dict:
        data = json.loads(content)
        if 'word_name' not in data:
            return None

        for s in data.get('symbols', []):
            s['ph_am_mp3_data'] = MP3Fetcher(s.get('ph_am_mp3')).start()
            s['ph_en_mp3_data'] = MP3Fetcher(s.get('ph_en_mp3')).start()
            s['ph_tts_mp3_data'] = MP3Fetcher(s.get('ph_tts_mp3')).start()

        for s in data.get('symbols', []):
            s['ph_am_mp3_data'] = s['ph_am_mp3_data'].join()
            s['ph_en_mp3_data'] = s['ph_en_mp3_data'].join()
            s['ph_tts_mp3_data'] = s['ph_tts_mp3_data'].join()

        data['sent'] =[]

        return data


class XMLICIFetcher(ICIFetcher):
    def __init__(self, word: str, *args, **kwargs):
        super().__init__(word=word, t='xml', *args, **kwargs)

    def _parser(self, content: bytes) -> dict:
        data = xmltodict.parse(content)
        ret = {'sent': []}

        for s in data['dict']['sent']:
            ret['sent'].append(dict(s))

        return ret


class NeoIci:
    def __init__(self):
        pass

    def fetch(self, word: str) -> dict:
        data = LDBFetcher(word).start().join()
        if data is not None:
            return data

        thread_json = JSONICIFetcher(word).start()
        thread_xml = XMLICIFetcher(word).start()

        data = thread_json.join()
        if data is None:
            return None

        data_xml = thread_xml.join()
        if data_xml is not None:
            data.update(data_xml)

        LDBPusher(word, data).start()
        return data


@pynvim.plugin
class NeoIciPlugin(object):
    def __init__(self, nvim: pynvim.Nvim):
        self._nvim = nvim
        self._neoici = NeoIci()

    def parse(self, result):
        extbl = {
            "word_pl": "复数",
            "word_past": "过去时",
            "word_done": "完成时",
            "word_ing": "进行时",
            "word_third": "第三人称单数",
            "word_er": "比较级",
            "word_est": "最高级",
        }
        data = result

        lines = ['### {}'.format(data['word_name'])]

        exchange_lines = []
        for k, v in data.get('exchange', {}).items():
            if v:
                exchange_lines.append(' * {}: {}'.format(
                    extbl[k], '; '.join(v)))

        if exchange_lines:
            lines.append('')
            lines.append('* exchange:')
            lines += exchange_lines

        played = False
        for s in data.get('symbols', []):
            lines.append('')
            ph = '*'
            if s.get('ph_am'):
                ph += ' US: [{}]'.format(s.get('ph_am'))
                if s.get('ph_am_mp3_data'):
                    ph += '🔇'
                    if not played:
                        song = AudioSegment.from_file(
                            io.BytesIO(s.get('ph_am_mp3_data')), format="mp3")
                        threading.Thread(
                            target=play, args=(song, ), daemon=True).start()
                        played = True

            if s.get('ph_en'):
                ph += ' UK: [{}]'.format(s.get('ph_en'))
                if s.get('ph_en_mp3_data'):
                    ph += '🔇'
                    if not played:
                        song = AudioSegment.from_file(
                            io.BytesIO(s.get('ph_en_mp3_data')), format="mp3")
                        threading.Thread(
                            target=play, args=(song, ), daemon=True).start()
                        played = True

            if s.get('ph_other'):
                pho = s.get('ph_other', '')
                if pho.startswith('http://res-tts.iciba.com'):
                    pho = pho[24:]

                if pho.startswith(','):
                    pho = pho[1:]

                ph += ' TTS: [{}]'.format(pho)
                if s.get('ph_tts_mp3_data'):
                    ph += '🔇'
                    if not played:
                        song = AudioSegment.from_file(
                            io.BytesIO(s.get('ph_tts_mp3_data')), format="mp3")
                        threading.Thread(
                            target=play, args=(song, ), daemon=True).start()
                        played = True

            if len(ph) > 1:
                lines.append(ph)

            for p in s['parts']:
                if p.get('part'):
                    lines.append(' * {}'.format(p['part']))

                for m in p['means']:
                    lines.append('  * {}'.format(m))
                lines.append('')

        for s in data.get('sent', []):
            lines.append('> {}'.format(s['orig']))
            lines.append('> {}'.format(s['trans']))
            lines.append('')

        return lines

    @pynvim.function('Ici', sync=True)
    def _ici(self, args):
        if args and isinstance(args[0], str):
            data = self._neoici.fetch(args[0])
            if data is None:
                return None

            return self.parse(data)
