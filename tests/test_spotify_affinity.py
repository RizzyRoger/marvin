"""Spotify affinity ranking prefers familiar albums/artists."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.tools.spotify import client as spotify_client


class SpotifyAffinityTests(unittest.TestCase):
    def test_album_beats_track_when_artist_in_top(self):
        affinity = {
            "artist_ids": {"nirvana"},
            "artist_names": {"nirvana"},
            "track_ids": set(),
            "album_ids": {"nevermind-album"},
            "album_names": {"nevermind"},
        }
        album = {
            "id": "nevermind-album",
            "name": "Nevermind",
            "uri": "spotify:album:1",
            "artists": [{"id": "nirvana", "name": "Nirvana"}],
        }
        track = {
            "id": "nevermind-track",
            "name": "Nevermind",
            "uri": "spotify:track:1",
            "artists": [{"id": "other", "name": "Other"}],
            "album": {"id": "x", "name": "X"},
        }
        album_bonus = spotify_client._affinity_bonus(album, "album", affinity)
        track_bonus = spotify_client._affinity_bonus(track, "track", affinity)
        self.assertGreater(album_bonus, track_bonus)

    def test_search_and_play_auto_prefers_affinity_album(self):
        affinity = {
            "artist_ids": {"nirvana"},
            "artist_names": {"nirvana"},
            "track_ids": set(),
            "album_ids": {"alb1"},
            "album_names": {"nevermind"},
        }
        album = {
            "id": "alb1",
            "name": "Nevermind",
            "uri": "spotify:album:alb1",
            "artists": [{"id": "nirvana", "name": "Nirvana"}],
            "available_markets": ["US"],
        }
        track = {
            "id": "trk1",
            "name": "Nevermind",
            "uri": "spotify:track:trk1",
            "artists": [{"id": "other", "name": "Someone Else"}],
            "album": {"id": "otheralb", "name": "Other"},
            "available_markets": ["US"],
        }

        def fake_request(method, path, params=None, **_kwargs):
            if path == "/search":
                st = params.get("type")
                if st == "album":
                    return {"albums": {"items": [album]}}
                if st == "track":
                    return {"tracks": {"items": [track]}}
                if st == "artist":
                    return {"artists": {"items": []}}
            raise AssertionError(f"unexpected {method} {path}")

        with (
            patch.object(spotify_client, "ensure_active_device", return_value="dev"),
            patch.object(spotify_client, "get_user_top_affinity", return_value=affinity),
            patch.object(spotify_client, "_user_market", return_value="US"),
            patch.object(spotify_client, "spotify_api_request", side_effect=fake_request),
            patch.object(spotify_client, "play_on_device") as play,
        ):
            msg = spotify_client.search_and_play("nevermind", kind="auto")
            self.assertIn("album", msg.lower())
            play.assert_called_once()
            body = play.call_args.kwargs.get("json_body") or play.call_args[1].get(
                "json_body"
            )
            self.assertEqual(body.get("context_uri"), "spotify:album:alb1")


if __name__ == "__main__":
    unittest.main()
