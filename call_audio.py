"""
Real LiveKit voice-call connection for SplusLib conference calls.

This module takes the `url` + `token` you get back from
`SplusClient.join_group_call(...)` (after the isinstance fix in client.py)
and does the part that spluslib/client.py never did: actually connecting
to the LiveKit room and publishing a real, streamable audio track so the
bot can be heard in the call.

Playback works by decoding whatever file you give it (mp3/ogg/wav/anything
ffmpeg understands) into raw PCM via an `ffmpeg` subprocess, then pushing
20ms frames into a LiveKit `AudioSource`. The audio TRACK is published
once, when you connect; switching or stopping songs just changes what's
being fed into that same track, so the switch is instant and doesn't
cause a disconnect/reconnect blip in the call the way re-publishing a new
track would.

Usage:

    from spluslib.client import SplusClient
    from spluslib.call_audio import CallAudioSession

    client = SplusClient("my_session")
    await client.start("+989123456789")

    call = await client.join_group_call(slug="atp-nwz-yux")
    # call now actually has 'url' and 'token' after the client.py fix

    session = CallAudioSession()
    await session.connect(call["url"], call["token"])

    await session.play("/path/to/song.mp3")   # start/queue playback
    ...
    await session.play("/path/to/other.mp3")  # switch track, instant
    ...
    await session.stop()                      # stop playback, stay in call
    ...
    await session.disconnect()                # leave the call entirely

Requires:
    pip install livekit --break-system-packages
    ffmpeg must be installed and on PATH (used only for decoding audio
    files to raw PCM; no python audio-decoding dependency needed).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Optional

from livekit import rtc

from . import errors

logger = logging.getLogger("spluslib.call_audio")

# LiveKit's recommended settings for a simple mono voice/music source.
# 48kHz mono is what LiveKit's Opus encoder expects; ffmpeg is told to
# output exactly this so no extra resampling step is needed on our side.
SAMPLE_RATE = 48000
NUM_CHANNELS = 1
FRAME_MS = 20  # LiveKit convention: push audio in 20ms frames
SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS // 1000  # 960 samples @ 48kHz/20ms
BYTES_PER_SAMPLE = 2  # 16-bit PCM
FRAME_BYTES = SAMPLES_PER_FRAME * NUM_CHANNELS * BYTES_PER_SAMPLE


class CallAudioSession:
    """
    Wraps a LiveKit Room + a single published audio track for one call.

    One instance = one active voice-call session. Create a new instance
    per call if you need to be in multiple conference calls at once.
    """

    def __init__(self):
        self._room: Optional[rtc.Room] = None
        self._source: Optional[rtc.AudioSource] = None
        self._track: Optional[rtc.LocalAudioTrack] = None
        self._publication: Optional[rtc.LocalTrackPublication] = None
        self._play_task: Optional[asyncio.Task] = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_playing(self) -> bool:
        return self._play_task is not None and not self._play_task.done()

    # ------------------------------------------------------------------ #
    # Connect / disconnect
    # ------------------------------------------------------------------ #

    async def connect(self, url: str, token: str) -> None:
        """
        Actually join the LiveKit room for the conference call, and
        publish one audio track (silent until you call play()).

        `url` and `token` come straight from
        SplusClient.join_group_call()'s return dict.
        """
        if self._connected:
            raise errors.AlreadyInCallError(
                "Already connected to a call. Call disconnect() first."
            )
        if not url or not token:
            raise errors.CallNotFoundError(
                "connect() needs both a LiveKit url and token. "
                "If these are missing/None, the JoinConferenceCallRequest "
                "response didn't carry an UpdateConferenceCallConnection "
                "update -- check that client.py's join_group_call is using "
                "isinstance(update, types.UpdateConferenceCallConnection) "
                "and not the old (broken) `update._` string check."
            )

        room = rtc.Room()

        @room.on("disconnected")
        def _on_disconnected(reason=None):
            logger.info("LiveKit room disconnected (reason=%s)", reason)
            self._connected = False

        @room.on("participant_connected")
        def _on_participant_connected(participant):
            logger.debug("Participant joined: %s", participant.identity)

        await room.connect(url, token, options=rtc.RoomOptions(auto_subscribe=True))
        self._room = room
        self._connected = True

        # Create the audio source + track once. We keep reusing this same
        # track for the whole call; play()/stop() just change what audio
        # data (if any) gets pushed into it.
        source = rtc.AudioSource(SAMPLE_RATE, NUM_CHANNELS)
        track = rtc.LocalAudioTrack.create_audio_track("bot-audio", source)

        publication = await room.local_participant.publish_track(
            track,
            rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE),
        )

        self._source = source
        self._track = track
        self._publication = publication

        logger.info("Connected to LiveKit room and published audio track")

    async def disconnect(self) -> None:
        """Stop any playback and leave the call entirely."""
        await self.stop()

        if self._room is not None:
            await self._room.disconnect()

        self._room = None
        self._source = None
        self._track = None
        self._publication = None
        self._connected = False
        logger.info("Disconnected from LiveKit room")

    # ------------------------------------------------------------------ #
    # Playback control
    # ------------------------------------------------------------------ #

    async def play(self, file_path: str, *, loop: bool = False) -> None:
        """
        Play (or switch to) an audio file. Works with mp3/ogg/wav/etc --
        anything ffmpeg can decode.

        If something is already playing, it is stopped first and this
        file starts immediately after -- the published track itself
        never changes, so there's no re-join/re-publish flicker in the
        call, just a clean cut from one source to the next.

        Set loop=True to keep repeating the file until stop() is called.
        """
        if not self._connected or self._source is None:
            raise errors.NotInCallError("Not connected. Call connect() first.")

        # Stop whatever is currently playing before starting the new one.
        await self._stop_playback_task()

        self._play_task = asyncio.create_task(
            self._stream_file_to_source(file_path, loop=loop)
        )
        logger.info("Started playback: %s (loop=%s)", file_path, loop)

    async def stop(self) -> None:
        """Stop playback. Stays connected to the call."""
        await self._stop_playback_task()
        logger.info("Playback stopped")

    async def wait_until_done(self) -> None:
        """
        Wait until the currently playing track finishes on its own
        (only meaningful for play(..., loop=False) -- with loop=True
        this will wait forever, since the track never ends by itself).

        Use this in scripts that just want to play one file and exit
        afterwards, e.g.:

            await session.play("song.mp3")
            await session.wait_until_done()
            await session.disconnect()

        If nothing is playing, returns immediately.
        """
        if self._play_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._play_task

    async def _stop_playback_task(self) -> None:
        if self._play_task is not None:
            self._play_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._play_task
            self._play_task = None

    # ------------------------------------------------------------------ #
    # Internal: decode with ffmpeg and push PCM frames into the source
    # ------------------------------------------------------------------ #

    async def _stream_file_to_source(self, file_path: str, *, loop: bool) -> None:
        while True:
            await self._play_once(file_path)
            if not loop:
                break

    async def _play_once(self, file_path: str) -> None:
        """
        Spawn ffmpeg to decode file_path to raw 48kHz/mono/s16le PCM on
        stdout, and feed it into the LiveKit AudioSource frame by frame,
        paced in real time so playback speed is correct.
        """
        cmd = [
            "ffmpeg",
            "-loglevel", "error",
            "-i", file_path,
            "-f", "s16le",
            "-ac", str(NUM_CHANNELS),
            "-ar", str(SAMPLE_RATE),
            "-",
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            assert process.stdout is not None
            frame_interval = FRAME_MS / 1000.0
            next_send_time = asyncio.get_event_loop().time()

            while True:
                chunk = await process.stdout.readexactly(FRAME_BYTES)
                frame = rtc.AudioFrame(
                    data=chunk,
                    sample_rate=SAMPLE_RATE,
                    num_channels=NUM_CHANNELS,
                    samples_per_channel=SAMPLES_PER_FRAME,
                )
                # NOTE: AudioSource.capture_frame is a coroutine in the
                # livekit python SDK (confirmed on 1.1.14) -- it must be
                # awaited. Calling it without await silently does nothing
                # (Python just creates a coroutine object and warns
                # "was never awaited"), which is why audio previously
                # joined the call but no sound was ever actually sent.
                await self._source.capture_frame(frame)

                # Pace ourselves to real playback speed instead of
                # dumping frames as fast as ffmpeg can decode them.
                next_send_time += frame_interval
                sleep_time = next_send_time - asyncio.get_event_loop().time()
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        except asyncio.IncompleteReadError:
            # Clean end of file -- last partial chunk is discarded, which
            # just trims a few ms of silence off the very end.
            pass
        except asyncio.CancelledError:
            raise
        finally:
            if process.returncode is None:
                process.kill()
                with contextlib.suppress(Exception):
                    await process.wait()

            if process.stderr is not None:
                with contextlib.suppress(Exception):
                    stderr = await process.stderr.read()
                    if process.returncode not in (None, 0) and stderr:
                        logger.warning(
                            "ffmpeg exited with error: %s",
                            stderr.decode(errors="ignore"),
                        )
