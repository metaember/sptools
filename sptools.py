import json
from pathlib import Path
from pprint import pprint
from typing import Optional

import click
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()


AVAILABLE_COMMANDS = ["saved_tracks", "now_playing"]

scopes = [
    "user-library-read",
    "user-read-currently-playing",
]
scope = " ".join(scopes)
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=scope))


def get_saved_tracks(limit: int = 1000):
    results = sp.current_user_saved_tracks(limit=limit)
    return results


def get_now_playing(full: bool = True):
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
    pass


def backup_playlist(playlist_id: str, json_path: Optional[str] = None):
    pass


def backup_all_playlists(json_path: Optional[str] = None):
    pass


def make_playlist_with_liked_but_not_playlisted_tracks():
    pass


def main(
    command,
    json_path: Optional[str] = None,
    print: bool = False,
    full: Optional[bool] = True,
    overwrite: bool = False,
):
    if command == "saved_tracks":
        result = get_saved_tracks(limit=1000 if full else 20)
    elif command == "now_playing":
        result = get_now_playing(full=full)

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
