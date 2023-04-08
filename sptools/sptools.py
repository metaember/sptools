import datetime
import json
from pathlib import Path
from pprint import pprint
from typing import Optional

import click
from dotenv import load_dotenv
from loguru import logger
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import tomli
from tinydb import TinyDB, Query


load_dotenv()


AVAILABLE_COMMANDS = ["backup", "now_playing", "compile_unplaylisted"]


scopes = [
    "user-library-read",
    "user-read-currently-playing",
    "playlist-read-private",
]

scope = " ".join(scopes)
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=scope))


def get_saved_tracks():
    """ Requires scope: user-library-read"""
    logger.debug("Getting saved tracks")

    MAX_LIMIT = 50
    tracks = []
    offset = 0
    while True:
        logger.debug(f"Getting saved tracks offset: {offset}")
        response = sp.current_user_saved_tracks(limit=MAX_LIMIT, offset=offset)
        tracks.extend(response["items"])
        offset += MAX_LIMIT
        if response["next"] is None:
            break

    return tracks


def get_now_playing(full: bool = True):
    """ Requires scope: user-read-currently-playing"""
    currently_playing = sp.currently_playing()
    if not full:
        return dict(
            title=currently_playing["item"]["name"],
            artists=[artist["name"] for artist in currently_playing["item"]["artists"]],
            # artists_string = ", ".join([artist["name"] for artist in artists]),
            # album_art_url = currently_playing["item"]["album"]["images"][-1]["url"],
            album_name=currently_playing["item"]["album"]["name"],
        )
    return currently_playing


def get_all_playlists():
    """ Return all the playlists, but without the tracks. """
    logger.debug("Getting all playlists")


    # 50 is the max limit for playlists
    MAX_LIMIT = 50

    playlists = []
    offset = 0
    while True:
        response = sp.current_user_playlists(limit=MAX_LIMIT, offset=offset)
        playlists.extend(response["items"])
        offset += MAX_LIMIT
        if response["next"] is None:
            break

    return playlists


def get_playlist(playlist_id: str):
    """ Get a playlist info, along with all the tracks. """
    logger.debug(f"Getting playlist: {playlist_id}")

    playlist_info = sp.playlist(playlist_id=playlist_id)

    if playlist_info["tracks"]["next"] is not None:
        # the first call did not return all the tracks
        tracks = get_playlist_tracks(playlist_id=playlist_id)
        playlist_info["tracks"]["items"] = tracks

    return playlist_info


def get_playlist_tracks(playlist_id: str):
    """ Get all the tracks for a playlist. """
    MAX_LIMIT = 100

    tracks = []
    offset = 0
    while True:
        response = sp.playlist_items(
            playlist_id=playlist_id, limit=MAX_LIMIT, offset=offset
        )
        tracks.extend(response["items"])
        offset += MAX_LIMIT
        if response["next"] is None:
            break

    return tracks


def backup(only_mine: bool = False):
    """ Run a full backup. """
    backup_time = datetime.datetime.now().isoformat()
    backup_saved_tracks(backup_time=backup_time)
    backup_all_playlists(only_mine=only_mine, backup_time=backup_time)


def backup_all_playlists(only_mine: bool = False, backup_time: Optional[datetime.datetime] = None):
    # this will be the key used to index the backup
    backup_time = datetime.datetime.now().isoformat() if backup_time is None else backup_time

    playlists = get_all_playlists()
    for playlist in playlists:
        if only_mine and playlist["owner"]["id"] != sp.me()["id"]:
            continue
        logger.info(f"Backing up playlist: {playlist['name']} id: {playlist['id']}")
        backup_playlist(playlist_id=playlist["id"], backup_time=backup_time)


def backup_playlist(playlist_id: str, backup_time: datetime.datetime):
    playlist = get_playlist(playlist_id=playlist_id)
    db = get_db()
    playlist_table = db.table("playlists")
    playlist["backup_time"] = backup_time
    playlist_table.insert(playlist)


def backup_saved_tracks(backup_time: Optional[datetime.datetime] = None):
    backup_time = datetime.datetime.now().isoformat() if backup_time is None else backup_time

    tracks = get_saved_tracks()
    db = get_db()
    saved_tracks_table = db.table("saved_tracks")
    for track in tracks:
        track["backup_time"] = backup_time
        saved_tracks_table.insert(track)


def get_most_recent_backup_time() -> datetime.datetime:
    db = get_db()
    saved_tracks_table = db.table("saved_tracks")
    backup_time = max(track["backup_time"] for track in saved_tracks_table.search(
        Query().backup_time.exists()))
    return datetime.datetime.fromisoformat(backup_time)


def make_playlist_with_liked_but_not_playlisted_tracks():
    """
    Get the database. Then, look at the latest backup_time, and pull all the liked songs and 
    all the playlists from it. Then, get all the liked songs, and remove the ones that are in
    the playlists. Then, create a new playlist with the remaining songs.

    TODO: support cases where the backup time for the playlists is different than the backup time
    for the saved tracks.
    """
    db = get_db()
    saved_tracks_table = db.table("saved_tracks")
    playlists_table = db.table("playlists")

    # get the latest backup time
    backup_time = get_most_recent_backup_time().isoformat()

    # get all the saved tracks and playlists from that backup time
    saved_tracks = saved_tracks_table.search(Query().backup_time == backup_time)
    playlists = playlists_table.search(Query().backup_time == backup_time)

    # get all the track ids from the playlists
    playlist_track_ids = set()
    for playlist in playlists:
        for track in playlist["tracks"]["items"]:
            playlist_track_ids.add(track["track"]["id"])

    # get all the track ids from the saved tracks
    saved_track_ids = set()
    for track in saved_tracks:
        saved_track_ids.add(track["track"]["id"])

    # get the track ids that are in the saved tracks, but not in the playlists
    track_ids_to_add = saved_track_ids - playlist_track_ids

    # get the track info for the tracks to add
    tracks_to_add_uri = []
    tracks_to_add = []
    for track_id in track_ids_to_add:
        track = sp.track(track_id)
        tracks_to_add_uri.append(track["uri"])
        tracks_to_add.append(track)

    # create the playlist
    playlist_name = f"Liked but not playlisted {backup_time}"
    playlist = sp.user_playlist_create(user=sp.me()["id"], name=playlist_name)

    # add the tracks to the playlist
    sp.playlist_add_items(playlist_id=playlist["id"], items=tracks_to_add_uri)
    return tracks_to_add


def main(
    command,
    json_path: Optional[str] = None,
    print: bool = False,
    full: Optional[bool] = True,
    overwrite: bool = False,
):
    if command == "backup":
        result = backup()
    elif command == "now_playing":
        result = get_now_playing(full=full)
    elif command == "compile_unplaylisted":
        result = make_playlist_with_liked_but_not_playlisted_tracks()
    else:
        raise ValueError(f"Unknown command: {command}")

    if print:
        pprint(result)

    if json_path is not None:
        json_path = Path(json_path)
        if json_path.is_file() and not overwrite:
            raise FileExistsError(f"File already exists: {json_path}")
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(result, indent=4))

    return result


def get_config() -> dict:
    return tomli.loads((Path(__file__).parent / "config.toml").read_text())


def get_db() -> TinyDB:
    config = get_config()
    db = TinyDB(config["db_file"])
    return db


@click.command()
@click.argument("command", type=click.Choice(AVAILABLE_COMMANDS))
@click.option("--json-file", type=click.Path())
@click.option(
    "--print", is_flag=True, help="Print the result to the console", default=False
)
@click.option(
    "--full/--short",
    is_flag=True,
    help="Print the full result or just a compact form",
    default=True,
)
@click.option(
    "--overwrite/--no-overwrite",
    is_flag=True,
    help="Overwrite existing files",
    default=False,
)
def cli(command: str, json_file: str, print: bool, full: bool, overwrite: bool):
    return main(command, json_file, print, full=full, overwrite=overwrite)


if __name__ == "__main__":
    cli()
