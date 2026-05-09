from ytmuxiris.models import Album, Playlist, Song


def test_song_equality():
    s1 = Song(video_id="abc", title="T", artist="A")
    s2 = Song(video_id="abc", title="Different", artist="B")
    assert s1 == s2


def test_song_hash_set():
    songs = {
        Song(video_id="abc", title="T", artist="A"),
        Song(video_id="abc", title="T", artist="A"),
    }
    assert len(songs) == 1


def test_album_defaults():
    album = Album(browse_id="x", title="Album", artist="Artist")
    assert album.tracks == []
    assert album.track_count == 0


def test_playlist_defaults():
    pl = Playlist(playlist_id="pl1", title="My Playlist")
    assert pl.tracks == []
    assert pl.description == ""
