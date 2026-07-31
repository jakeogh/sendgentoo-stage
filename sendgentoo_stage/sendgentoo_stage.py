#!/usr/bin/env python3

import os
import sys
from contextlib import chdir
from pathlib import Path
from signal import SIG_DFL
from signal import SIGPIPE
from signal import signal

import click
import hs
from asserttool import ic
from asserttool import icp
from click_auto_help import AHGroup
from clicktool import click_add_options
from clicktool import click_arch_select
from clicktool import click_global_options
from clicktool import tvicgvd
from eprint import eprint
from getdents import paths
from globalverbose import gvd
from mounttool import path_is_mounted
from nettool import download_file
from pathtool import path_is_file
from proxytool import construct_proxy_dict

signal(SIGPIPE, SIG_DFL)

_gpg = hs.Command("gpg")

STAGE3_KEY_FINGERPRINTS = (
    "0xBB572E0E2D182910",
    "534E4209AB49EEE1C19D96162C44695DB9F6043D",
)
STAGE3_KEYS_NAME = "keys.asc"


def fetch_gpg_key(fingerprint: str) -> None:
    # keyserver access, so this runs only where there is internet
    try:
        _gpg("--fingerprint", fingerprint)
    except hs.ErrorReturnCode_2:
        _gpg(
            "--keyserver",
            "hkps://keys.gentoo.org",
            "--recv-keys",
            fingerprint,
            _out=sys.stdout,
            _err=sys.stderr,
        )


def export_stage3_keys(*, destination: Path) -> Path:
    # exported where there is internet so a machine without it can verify the
    # signature without reaching a keyserver
    for fingerprint in STAGE3_KEY_FINGERPRINTS:
        fetch_gpg_key(fingerprint)
    _gpg(
        "--yes",
        "--armor",
        "--output",
        destination.as_posix(),
        "--export",
        *STAGE3_KEY_FINGERPRINTS,
        _out=sys.stdout,
        _err=sys.stderr,
    )
    return destination


def import_stage3_keys(*, keys_url: str, proxy_dict: None | dict) -> None:
    destination_dir = Path("/var/tmp/sendgentoo_stage/")
    os.makedirs(destination_dir, exist_ok=True)
    keys_file = download_file(
        url=keys_url,
        destination_dir=destination_dir,
        proxy_dict=proxy_dict,
    )
    _gpg("--import", str(keys_file), _out=sys.stdout, _err=sys.stderr)


def get_stage3_url(
    stdlib: str,
    arch: str,
    proxy_dict: None | dict,
    verbose: bool = False,
) -> str:
    assert isinstance(arch, str)
    assert len(arch) > 0

    # https://bugs.gentoo.org/931947
    mirror = f"http://gentoo.osuosl.org/releases/{arch}/autobuilds/"
    if stdlib == "glibc":
        latest = f"latest-stage3-{arch}-hardened-openrc.txt"
    elif stdlib == "musl":
        latest = f"latest-stage3-{arch}-musl-hardened.txt"
    else:
        raise ValueError(f"unknown stdlib: {stdlib}")

    get_url = mirror + latest
    ic(get_url)
    text = download_file(
        url=get_url,
        proxy_dict=proxy_dict,
    )
    icp(text)
    path = ""
    for line in text.split("\n"):
        if f"stage3-{arch}" in line:
            path = line.split(" ")[0]
            break
    assert "stage3" in path
    return mirror + path


def download_stage3(
    *,
    url: str,
    proxy_dict: None | dict,
    verbose: bool = False,
) -> Path:
    # the url is always explicit: a machine without internet is handed one
    # pointing at the deployment server, and resolving a mirror is a separate
    # operation that only runs where there is internet
    destination_dir = Path("/var/tmp/sendgentoo_stage/")  # unpriv user
    os.makedirs(destination_dir, exist_ok=True)
    icp(url)
    stage3_file = download_file(
        url=url,
        destination_dir=destination_dir,
        proxy_dict=proxy_dict,
        progress=True,
    )
    download_file(
        url=url + ".asc",
        destination_dir=destination_dir,
        proxy_dict=proxy_dict,
    )
    return Path(stage3_file)


def _assert_empty_root() -> None:
    _entries = list(
        paths(
            ".",
            min_depth=1,
            max_depth=0,
        )
    )
    icp(_entries)
    assert len(_entries) == 2  # just 'boot' and 'lost+found'


def extract_stage3(
    *,
    url: str,
    keys_url: str,
    destination: Path,
    expect_mounted_destination: bool,
    verbose: bool = False,
) -> None:
    destination = Path(destination).resolve()
    icp(
        url,
        destination,
    )
    if expect_mounted_destination:
        assert path_is_mounted(destination)

    with chdir(destination):
        proxy_dict = construct_proxy_dict()
        stage3_file = download_stage3(
            url=url,
            proxy_dict=proxy_dict,
        )
        assert path_is_file(stage3_file)
        _assert_empty_root()

        import_stage3_keys(keys_url=keys_url, proxy_dict=proxy_dict)

        ic(stage3_file)
        _gpg(
            "--verify",
            "--verbose",
            stage3_file.as_posix() + ".asc",
            _out=sys.stdout,
            _err=sys.stderr,
        )

        _assert_empty_root()
        hs.Command("tar")(
            "--xz",
            "-x",
            "-p",
            "-f",
            stage3_file.as_posix(),
            "-C",
            destination.as_posix(),
            _out=sys.stdout,
            _err=sys.stderr,
        )


@click.group(no_args_is_help=True, cls=AHGroup)
@click_add_options(click_global_options)
@click.pass_context
def cli(
    ctx: click.Context,
    verbose_inf: bool,
    dict_output: bool,
    verbose: bool = False,
) -> None:
    tty, verbose = tvicgvd(
        ctx=ctx,
        verbose=verbose,
        verbose_inf=verbose_inf,
        ic=ic,
        gvd=gvd,
    )


@cli.command("get-stage3-url")
@click.option(
    "--stdlib",
    is_flag=False,
    required=True,
    type=click.Choice(["glibc", "musl"]),
)
@click.option("--proxy", is_flag=True)
@click_add_options(click_arch_select)
@click_add_options(click_global_options)
@click.pass_context
def _get_stage3_url(
    ctx: click.Context,
    stdlib: str,
    arch: str,
    proxy: bool,
    verbose_inf: bool,
    dict_output: bool,
    verbose: bool = False,
) -> None:
    tty, verbose = tvicgvd(
        ctx=ctx,
        verbose=verbose,
        verbose_inf=verbose_inf,
        ic=ic,
        gvd=gvd,
    )

    proxy_dict = None
    if proxy:
        proxy_dict = construct_proxy_dict()
    url = get_stage3_url(
        stdlib=stdlib,
        arch=arch,
        proxy_dict=proxy_dict,
    )
    eprint(url)


@cli.command("download-stage3")
@click.option(
    "--stdlib",
    is_flag=False,
    required=True,
    type=click.Choice(["glibc", "musl"]),
)
@click.option("--proxy", is_flag=True)
@click_add_options(click_arch_select)
@click_add_options(click_global_options)
@click.pass_context
def _download_stage3(
    ctx: click.Context,
    stdlib: str,
    arch: str,
    proxy: bool,
    verbose_inf: bool,
    dict_output: bool,
    verbose: bool = False,
) -> None:
    tty, verbose = tvicgvd(
        ctx=ctx,
        verbose=verbose,
        verbose_inf=verbose_inf,
        ic=ic,
        gvd=gvd,
    )

    proxy_dict = None
    if proxy:
        proxy_dict = construct_proxy_dict()
    url = get_stage3_url(
        stdlib=stdlib,
        arch=arch,
        proxy_dict=proxy_dict,
    )
    download_stage3(
        url=url,
        proxy_dict=proxy_dict,
    )


@cli.command("export-stage3-keys")
@click.argument(
    "destination",
    type=click.Path(
        exists=False,
        dir_okay=False,
        file_okay=True,
        allow_dash=False,
        path_type=Path,
    ),
    nargs=1,
    required=True,
)
@click_add_options(click_global_options)
@click.pass_context
def _export_stage3_keys(
    ctx: click.Context,
    destination: Path,
    verbose_inf: bool,
    dict_output: bool,
    verbose: bool = False,
) -> None:
    tty, verbose = tvicgvd(
        ctx=ctx,
        verbose=verbose,
        verbose_inf=verbose_inf,
        ic=ic,
        gvd=gvd,
    )

    export_stage3_keys(destination=destination)


@cli.command("extract-stage3")
@click.argument(
    "destination",
    type=click.Path(
        exists=False,
        dir_okay=True,
        file_okay=False,
        allow_dash=False,
        path_type=Path,
    ),
    nargs=1,
    required=True,
)
@click.option("--url", is_flag=False, required=True, type=str)
@click.option("--keys-url", is_flag=False, required=True, type=str)
@click_add_options(click_global_options)
@click.pass_context
def _extract_stage3(
    ctx: click.Context,
    destination: Path,
    url: str,
    keys_url: str,
    verbose_inf: bool,
    dict_output: bool,
    verbose: bool = False,
) -> None:
    tty, verbose = tvicgvd(
        ctx=ctx,
        verbose=verbose,
        verbose_inf=verbose_inf,
        ic=ic,
        gvd=gvd,
    )

    extract_stage3(
        url=url,
        keys_url=keys_url,
        destination=destination,
        expect_mounted_destination=False,
    )
