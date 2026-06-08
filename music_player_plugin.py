#!/usr/bin/env python3
"""Plugin Music Player"""
class MusicPlayerPlugin:
    def __init__(self, manager):
        self.manager = manager
        self.playing = None

    def play(self, query=""):
        print(f"PLAY: {query}")
        self.playing = query
        return {"playing": query}

    def stop(self):
        print("STOP music")
        self.playing = None
        return {"status": "stopped"}

    def pause(self):
        print("PAUSE")
        return {"status": "paused"}

    def next(self):
        print("NEXT")
        return {"status": "next"}

    def prev(self):
        print("PREV")
        return {"status": "prev"}

    def now_playing(self):
        return f"♪ {self.playing}" if self.playing else "No music"