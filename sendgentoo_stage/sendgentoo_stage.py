#!/usr/bin/env python3
# -*- coding: utf8 -*-

# flake8: noqa           # flake8 has no per file settings :(
# pylint: disable=C0111  # docstrings are always outdated and wrong
# pylint: disable=C0114  #      Missing module docstring (missing-module-docstring)
# pylint: disable=W0511  # todo is encouraged
# pylint: disable=C0301  # line too long
# pylint: disable=R0902  # too many instance attributes
# pylint: disable=C0302  # too many lines in module
# pylint: disable=C0103  # single letter var names, func name too descriptive
# pylint: disable=R0911  # too many return statements
# pylint: disable=R0912  # too many branches
# pylint: disable=R0915  # too many statements
# pylint: disable=R0913  # too many arguments
# pylint: disable=R1702  # too many nested blocks
# pylint: disable=R0914  # too many local variables
# pylint: disable=R0903  # too few public methods
# pylint: disable=E1101  # no member for base
# pylint: disable=W0201  # attribute defined outside __init__
# pylint: disable=R0916  # Too many boolean expressions in if statement
# pylint: disable=C0305  # Trailing newlines editor should fix automatically, pointless warning
# pylint: disable=C0413  # TEMP isort issue [wrong-import-position] Import "from pathlib import Path" should be placed at the top of the module [C0413]

import os
import sys
from pathlib import Path
from signal import SIG_DFL
from signal import SIGPIPE
from signal import signal
# from subprocess import CalledProcessError
# from typing import ByteString
from typing import Generator
from typing import Iterable
from typing import List
from typing import Optional
from typing import Union

import click
import sh
from asserttool import ic
from clicktool import click_add_options
from clicktool import click_arch_select
from clicktool import click_global_options
from clicktool import tv
from eprint import eprint
from getdents import paths
from mounttool import path_is_mounted
from nettool import construct_proxy_dict
from nettool import download_file
from pathtool import path_is_file
from with_chdir import chdir

signal(SIGPIPE, SIG_DFL)


def get_stage3_url(
    stdlib: str,
    multilib: bool,
    arch: str,
    proxy_dict: dict,
    verbose: Union[bool, int, float],
):

    # mirror = 'http://ftp.ucsb.edu/pub/mirrors/linux/gentoo/releases/amd64/autobuilds/'
    mirror = "http://gentoo.osuosl.org/releases/" + arch + "/autobuilds/"
    if stdlib == "glibc":
        if not multilib:
            latest = "latest-stage3-" + arch + "-hardened-nomultilib-openrc.txt"
        else:
            latest = "latest-stage3-" + arch + "-hardened-openrc.txt"

    if stdlib == "musl":
        # return "http://gentoo.osuosl.org/releases/amd64/autobuilds/current-stage3-amd64-musl-hardened/stage3-amd64-hardened-nomultilib-openrc-20211003T170529Z.tar.xz"
        assert not multilib
        latest = "latest-stage3-" + arch + "-musl-hardened.txt"

    if stdlib == "uclibc":
        latest = "latest-stage3-" + arch + "-uclibc-hardened.txt"
        raise ValueError("uclibc not supported, wont compile efivars")

    get_url = mirror + latest
    if verbose:
        ic(get_url)
    text = download_file(
        url=get_url,
        proxy_dict=proxy_dict,
        verbose=verbose,
    )
    # r = requests.get(mirror + latest)
    ic(text)
    autobuild_file_lines = text.split("\n")
    # r.close()
    path = ""
    for line in autobuild_file_lines:
        if "stage3-" + arch in line:
            path = line.split(" ")[0]
            break
    # eprint('path:', path)
    assert "stage3" in path
    url = mirror + path
    # eprint("url:", url)
    return url


def download_stage3(
    *,
    stdlib: str,
    multilib: bool,
    arch: str,
    proxy_dict: dict,
    verbose: Union[bool, int, float],
):

    destination_dir = Path("/var/tmp/sendgentoo_stage/")  # unpriv user
    os.makedirs("/var/tmp/sendgentoo_stage/", exist_ok=True)
    url = get_stage3_url(
        proxy_dict=proxy_dict,
        stdlib=stdlib,
        multilib=multilib,
        arch=arch,
        verbose=verbose,
    )
    ic(url)
    stage3_file = download_file(
        url=url,
        destination_dir=destination_dir,
        proxy_dict=proxy_dict,
        verbose=verbose,
    )
    download_file(
        url=url + ".CONTENTS",
        destination_dir=destination_dir,
        proxy_dict=proxy_dict,
        verbose=verbose,
    )
    download_file(
        url=url + ".DIGESTS",
        destination_dir=destination_dir,
        proxy_dict=proxy_dict,
        verbose=verbose,
    )
    download_file(
        url=url + ".asc",
        destination_dir=destination_dir,
        proxy_dict=proxy_dict,
        verbose=verbose,
    )
    return Path(stage3_file)


def extract_stage3(
    *,
    stdlib: str,
    multilib: bool,
    arch: str,
    destination: Path,
    expect_mounted_destination: bool,
    vm: Optional[str],
    vm_ram: Optional[int],
    verbose: Union[bool, int, float],
):

    destination = Path(destination).resolve()
    ic(stdlib, multilib, arch, destination, vm)
    ic(destination)
    if expect_mounted_destination:
        assert path_is_mounted(
            destination,
            verbose=verbose,
        )

    with chdir(
        destination,
        verbose=verbose,
    ):
        ic(os.getcwd())
        ic(destination.as_posix())
        assert os.getcwd() == destination.as_posix()
        proxy_dict = construct_proxy_dict(
            verbose=verbose,
        )
        # url = get_stage3_url(stdlib=stdlib, multilib=multilib, arch=arch, proxy_dict=proxy_dict)
        # stage3_file = download_stage3(stdlib=stdlib, multilib=multilib, url=url, arch=arch, proxy_dict=proxy_dict)
        stage3_file = download_stage3(
            stdlib=stdlib,
            multilib=multilib,
            arch=arch,
            proxy_dict=proxy_dict,
            verbose=verbose,
        )
        assert path_is_file(stage3_file)
        # ic(list(paths(".", max_depth=0, verbose=verbose)))  # bug, includes parent
        ic(list(paths(".", min_depth=1, max_depth=0, verbose=verbose)))
        assert (
            len(list(paths(".", min_depth=1, max_depth=0, verbose=verbose))) == 2
        )  # just 'boot' and 'lost+found'

        # this never worked
        # gpg = gnupg.GPG(verbose=True)
        # import_result = gpg.recv_keys('keyserver.ubuntu.com', '0x2D182910')
        # ceprint(import_result)

        ## this works sometimes, but now complaines abut no dirmngr
        # gpg_cmd = 'gpg --keyserver keyserver.ubuntu.com --recv-key 0x2D182910'
        ##if proxy:
        ##    keyserver_options = " --keyserver-options http_proxy=http://" + proxy
        ##    gpg_cmd += keyserver_options
        # run_command(gpg_cmd, verbose=True)

        ic(stage3_file)
        sh.gpg(
            "--verify",
            "--verbose",
            stage3_file.as_posix() + ".asc",
            _out=sys.stdout,
            _err=sys.stderr,
        )

        # whirlpool = run_command("openssl dgst -r -whirlpool " + stage3_file.as_posix() + "| cut -d ' ' -f 1",
        #                        verbose=True).decode('utf8').strip()
        # try:
        #    run_command("/bin/grep " + whirlpool + ' ' + stage3_file.as_posix() + '.DIGESTS', verbose=True)
        # except CalledProcessError:
        #    ic('BAD WHIRPOOL HASH:', whirlpool)
        #    ic('For file:', stage3_file)
        #    ic('File is corrupt (most likely partially downloaded). Delete it and try again.')
        #    sys.exit(1)

        # assert len(list(paths(".", verbose=verbose))) == 1  # empty directory
        assert (
            len(list(paths(".", min_depth=1, max_depth=0, verbose=verbose))) == 2
        )  # just 'boot' and 'lost+found'
        sh.tar(
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


@click.group(no_args_is_help=True)
@click_add_options(click_global_options)
@click.pass_context
def cli(
    ctx,
    verbose: Union[bool, int, float],
    verbose_inf: bool,
    dict_input: bool,
):

    tty, verbose = tv(
        ctx=ctx,
        verbose=verbose,
        verbose_inf=verbose_inf,
    )


@cli.command("get-stage3-url")
@click.option(
    "--stdlib",
    is_flag=False,
    required=True,
    type=click.Choice(["glibc", "musl", "uclibc"]),
)
@click.option(
    "--multilib",
    is_flag=True,
)
@click.option("--proxy", is_flag=True)
@click_add_options(click_arch_select)
@click_add_options(click_global_options)
@click.pass_context
def _get_stage3_url(
    ctx,
    stdlib: str,
    multilib: bool,
    arch: str,
    proxy: bool,
    verbose: Union[bool, int, float],
    verbose_inf: bool,
    dict_input: bool,
):

    tty, verbose = tv(
        ctx=ctx,
        verbose=verbose,
        verbose_inf=verbose_inf,
    )

    proxy_dict = None
    if proxy:
        proxy_dict = construct_proxy_dict(
            verbose=verbose,
        )
    url = get_stage3_url(
        stdlib=stdlib,
        multilib=multilib,
        arch=arch,
        proxy_dict=proxy_dict,
        verbose=verbose,
    )
    eprint(url)


@cli.command("download-stage3")
@click.option(
    "--stdlib",
    is_flag=False,
    required=True,
    type=click.Choice(["glibc", "musl", "uclibc"]),
)
@click.option("--multilib", is_flag=True, required=False)
@click.option("--proxy", is_flag=True)
@click_add_options(click_arch_select)
@click_add_options(click_global_options)
@click.pass_context
def _download_stage3(
    ctx,
    stdlib: str,
    arch: str,
    multilib: bool,
    proxy: str,
    verbose: Union[bool, int, float],
    verbose_inf: bool,
    dict_input: bool,
):

    tty, verbose = tv(
        ctx=ctx,
        verbose=verbose,
        verbose_inf=verbose_inf,
    )

    proxy_dict = None
    if proxy:
        proxy_dict = construct_proxy_dict(
            verbose=verbose,
        )
    download_stage3(
        stdlib=stdlib,
        multilib=multilib,
        arch=arch,
        proxy_dict=proxy_dict,
        verbose=verbose,
    )


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
@click.option(
    "--stdlib",
    is_flag=False,
    required=True,
    type=click.Choice(["glibc", "musl", "uclibc"]),
)
@click.option("--multilib", is_flag=True, required=False)
@click.option("--proxy", is_flag=True)
@click_add_options(click_arch_select)
@click_add_options(click_global_options)
@click.pass_context
def _extract_stage3(
    ctx,
    destination: Path,
    stdlib: str,
    arch: str,
    multilib: bool,
    proxy: str,
    verbose: Union[bool, int, float],
    verbose_inf: bool,
    dict_input: bool,
):

    tty, verbose = tv(
        ctx=ctx,
        verbose=verbose,
        verbose_inf=verbose_inf,
    )

    proxy_dict = None
    if proxy:
        proxy_dict = construct_proxy_dict(
            verbose=verbose,
        )

    extract_stage3(
        stdlib=stdlib,
        arch=arch,
        multilib=multilib,
        destination=destination,
        expect_mounted_destination=False,
        vm=None,
        vm_ram=None,
        verbose=verbose,
    )
