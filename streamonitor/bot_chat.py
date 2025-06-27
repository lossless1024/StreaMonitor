import datetime
import os
import time
from textwrap import wrap
from threading import Thread


class _ChatLogFile:
    EXTENSION = None

    def __init__(self, username, video_filename):
        logfile_filename = os.path.splitext(video_filename)[0] + self.EXTENSION
        self._fd = open(logfile_filename, 'w')

    def __del__(self):
        self._fd.close()
        self._fd = None

    def writeInitialMessage(self, timestamp, relative_time, username, message):
        return

    def writeMessage(self, timestamp, relative_time, username, message):
        raise NotImplementedError()


class ChatPlainLog(_ChatLogFile):
    EXTENSION = '_chat.log'

    def __init__(self, username, video_filename):
        super().__init__(username, video_filename)
        self.writeInitialMessage = self.writeMessage

    def writeMessage(self, timestamp, relative_time, username, message):
        str_relative_time = time.strftime('%H:%M:%S', time.gmtime(relative_time))
        self._fd.write(f"{timestamp!s} - {str_relative_time} - {username}: {message}\n")
        self._fd.flush()


class ChatSubtitleSCC(_ChatLogFile):
    EXTENSION = '.scc'

    def __init__(self, username, video_filename):
        super().__init__(username, video_filename)
        self._fd.write('SCC_disassembly V1.2\nCHANNEL 1\n\n')

    def writeMessage(self, timestamp, relative_time, username, message):
        str_relative_time = time.strftime('%H:%M:%S', time.gmtime(relative_time))
        self._fd.write(str_relative_time + ':00     {RU3}{CR}{1504}' + username + ': ' + message + '\n')
        self._fd.flush()


class ChatSubtitleSRT(_ChatLogFile):
    EXTENSION = '.srt'
    VISIBLE_DURATION = 3
    WRAP_LENGTH = 70

    def __init__(self, username, video_filename):
        super().__init__(username, video_filename)
        self._counter = 1

    def _format_timestamp(self, timestamp):
        return time.strftime('%H:%M:%S', time.gmtime(timestamp)) + ',' + '{:.3f}'.format(timestamp-int(timestamp))[2:]

    def writeMessage(self, timestamp, relative_time, username, message):
        self._fd.write(f'{self._counter!s}\n')
        self._counter += 1

        str_relative_time = self._format_timestamp(relative_time)
        str_relative_time_end = self._format_timestamp(relative_time + self.VISIBLE_DURATION)
        self._fd.write(f'{str_relative_time} --> {str_relative_time_end}\n')

        text_parts = wrap(f'{username}: {message}', self.WRAP_LENGTH)
        if len(username) + 1 < self.WRAP_LENGTH:
            self._fd.write('<b>' + username + '</b>' + text_parts[0][len(username):] + '\n')
        else:
            self._fd.write(text_parts[0] + '\n')

        for part in text_parts[1:]:
            self._fd.write(part + '\n')
        self._fd.write('\n')
        self._fd.flush()


class ChatCollectingMixin:
    CHAT_LOG_FORMATS = [ChatPlainLog, ChatSubtitleSRT]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def prepareChatLog(self, message_callback):
        pass

    def startChatLog(self):
        pass

    def stopChatLog(self):
        pass

    def getVideoWrapper(self, url, filename):
        start_timestamp = datetime.datetime.now().timestamp()

        chat_log_files = []
        for format_class in self.CHAT_LOG_FORMATS:
            chat_log_files.append(format_class(self.username, filename))

        def handle_chat_message(username, message, timestamp=None, initial=False):
            if not timestamp:
                timestamp = datetime.datetime.now().timestamp()
            relative_time = timestamp - start_timestamp
            for file in chat_log_files:
                if initial:
                    file.writeInitialMessage(timestamp, relative_time, username, message)
                else:
                    file.writeMessage(timestamp, relative_time, username, message)

        self.prepareChatLog(handle_chat_message)
        chat_thread = Thread(target=self.startChatLog)
        chat_thread.start()

        super().getVideoWrapper(url, filename)
        self.stopChatLog()
        del chat_log_files[:]
