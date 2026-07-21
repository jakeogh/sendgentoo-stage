#!/usr/bin/env python3
# -*- coding: utf8 -*-


from __future__ import annotations

import os
import sys
from pathlib import Path
from signal import SIG_DFL
from signal import SIGPIPE
from signal import signal

import click
import sh
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
from with_chdir import chdir

signal(SIGPIPE, SIG_DFL)


def get_gpg_key(fingerprint: str):
    try:
        sh.gpg("--fingerprint", fingerprint)
    except sh.ErrorReturnCode_2:
        sh.gpg(
            "--keyserver",
            "hkps://keys.gentoo.org",
            "--recv-keys",
            fingerprint,
            _out=sys.stdout,
            _err=sys.stderr,
        )


def get_stage3_url(
    stdlib: str,
    arch: str,
    proxy_dict: dict,
    verbose: bool = False,
):
    assert isinstance(arch, str)
    assert len(arch) > 0

    # https://bugs.gentoo.org/931947
    mirror = "http://gentoo.osuosl.org/releases/" + arch + "/autobuilds/"
    if stdlib == "glibc":
        latest = "latest-stage3-" + arch + "-hardened-openrc.txt"
        # if not multilib:
        #    latest = "latest-stage3-" + arch + "-hardened-nomultilib-openrc.txt"
        # else:
        #    latest = "latest-stage3-" + arch + "-hardened-openrc.txt"

    elif stdlib == "musl":
        # return "http://gentoo.osuosl.org/releases/amd64/autobuilds/current-stage3-amd64-musl-hardened/stage3-amd64-hardened-nomultilib-openrc-20211003T170529Z.tar.xz"
        latest = "latest-stage3-" + arch + "-musl-hardened.txt"

    elif stdlib == "uclibc":
        latest = "latest-stage3-" + arch + "-uclibc-hardened.txt"
        raise ValueError("uclibc not supported, wont compile efivars")
    else:
        raise ValueError(f"unknown stdlib: {stdlib}")

    get_url = mirror + latest
    ic(get_url)
    text = download_file(
        url=get_url,
        proxy_dict=proxy_dict,
    )
    # r = requests.get(mirror + latest)
    icp(text)
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
    arch: str,
    proxy_dict: dict,
    verbose: bool = False,
):
    assert isinstance(arch, str)
    assert len(arch) > 0
    destination_dir = Path("/var/tmp/sendgentoo_stage/")  # unpriv user
    os.makedirs("/var/tmp/sendgentoo_stage/", exist_ok=True)
    url = get_stage3_url(
        proxy_dict=proxy_dict,
        stdlib=stdlib,
        arch=arch,
    )
    icp(url)
    stage3_file = download_file(
        url=url,
        destination_dir=destination_dir,
        proxy_dict=proxy_dict,
    )
    download_file(
        url=url + ".CONTENTS",
        destination_dir=destination_dir,
        proxy_dict=proxy_dict,
    )
    download_file(
        url=url + ".DIGESTS",
        destination_dir=destination_dir,
        proxy_dict=proxy_dict,
    )
    download_file(
        url=url + ".asc",
        destination_dir=destination_dir,
        proxy_dict=proxy_dict,
    )
    return Path(stage3_file)


def extract_stage3(
    *,
    stdlib: str,
    arch: str,
    destination: Path,
    expect_mounted_destination: bool,
    vm: None | str,
    vm_ram: None | int,
    verbose: bool = False,
):
    assert isinstance(arch, str)
    assert len(arch) > 0
    destination = Path(destination).resolve()
    icp(
        stdlib,
        arch,
        destination,
        vm,
    )
    icp(destination)
    if expect_mounted_destination:
        assert path_is_mounted(
            destination,
        )

    with chdir(
        destination,
    ):
        icp(os.getcwd())
        icp(destination.as_posix())
        assert os.getcwd() == destination.as_posix()
        proxy_dict = construct_proxy_dict()
        stage3_file = download_stage3(
            stdlib=stdlib,
            arch=arch,
            proxy_dict=proxy_dict,
        )
        assert path_is_file(stage3_file)
        # icp(list(paths(".", max_depth=0,)))  # bug, includes parent
        icp(list(paths(".", min_depth=1, max_depth=0)))
        assert (
            len(
                list(
                    paths(
                        ".",
                        min_depth=1,
                        max_depth=0,
                    )
                )
            )
            == 2
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

        get_gpg_key("0xBB572E0E2D182910")
        get_gpg_key("534E4209AB49EEE1C19D96162C44695DB9F6043D")

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
            len(
                list(
                    paths(
                        ".",
                        min_depth=1,
                        max_depth=0,
                    )
                )
            )
            == 2
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


@click.group(no_args_is_help=True, cls=AHGroup)
@click_add_options(click_global_options)
@click.pass_context
def cli(
    ctx,
    verbose_inf: bool,
    dict_output: bool,
    verbose: bool = False,
):
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
    type=click.Choice(["glibc", "musl", "uclibc"]),
)
@click.option("--proxy", is_flag=True)
@click_add_options(click_arch_select)
@click_add_options(click_global_options)
@click.pass_context
def _get_stage3_url(
    ctx,
    stdlib: str,
    arch: str,
    proxy: bool,
    verbose_inf: bool,
    dict_output: bool,
    verbose: bool = False,
):
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
    type=click.Choice(["glibc", "musl", "uclibc"]),
)
@click.option("--proxy", is_flag=True)
@click_add_options(click_arch_select)
@click_add_options(click_global_options)
@click.pass_context
def _download_stage3(
    ctx,
    stdlib: str,
    arch: str,
    proxy: str,
    verbose_inf: bool,
    dict_output: bool,
    verbose: bool = False,
):
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
    download_stage3(
        stdlib=stdlib,
        arch=arch,
        proxy_dict=proxy_dict,
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
@click.option("--proxy", is_flag=True)
@click_add_options(click_arch_select)
@click_add_options(click_global_options)
@click.pass_context
def _extract_stage3(
    ctx,
    destination: Path,
    stdlib: str,
    arch: str,
    proxy: str,
    verbose_inf: bool,
    dict_output: bool,
    verbose: bool = False,
):
    tty, verbose = tvicgvd(
        ctx=ctx,
        verbose=verbose,
        verbose_inf=verbose_inf,
        ic=ic,
        gvd=gvd,
    )

    proxy_dict = None
    # todo
    if proxy:
        proxy_dict = construct_proxy_dict()

    extract_stage3(
        stdlib=stdlib,
        arch=arch,
        destination=destination,
        expect_mounted_destination=False,
        vm=None,
        vm_ram=None,
    )
