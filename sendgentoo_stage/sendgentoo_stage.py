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
import time
from pathlib import Path
from signal import SIG_DFL
from signal import SIGPIPE
from signal import signal

import click
import sh
from asserttool import ic
from nettool import construct_proxy_dict
from nettool import download_file

signal(SIGPIPE, SIG_DFL)
from pathlib import Path
from subprocess import CalledProcessError
from typing import ByteString
from typing import Generator
from typing import Iterable
from typing import List
from typing import Optional
from typing import Sequence
from typing import Tuple
from typing import Union

from asserttool import eprint
from asserttool import nevd
from asserttool import verify
from clicktool import add_options
from clicktool import click_arch_select
from getdents import paths
from mounttool import path_is_mounted
from pathtool import path_is_file
from retry_on_exception import retry_on_exception
from run_command import run_command
from with_chdir import chdir


def get_stage3_url(stdlib: str,
                   multilib: bool,
                   arch: str,
                   proxy_dict: dict,
                   ):
    #mirror = 'http://ftp.ucsb.edu/pub/mirrors/linux/gentoo/releases/amd64/autobuilds/'
    mirror = 'http://gentoo.osuosl.org/releases/' + arch + '/autobuilds/'
    if stdlib == 'glibc':
        if not multilib:
            latest = 'latest-stage3-' + arch + '-hardened-nomultilib-openrc.txt'
        else:
            latest = 'latest-stage3-' + arch + '-hardened-openrc.txt'
    if stdlib == 'musl':
        return "http://gentoo.osuosl.org/releases/amd64/autobuilds/current-stage3-amd64-musl-hardened/stage3-amd64-hardened-nomultilib-openrc-20211003T170529Z.tar.xz"
        if not multilib:
            latest = 'latest-stage3-' + arch + 'musl-hardened-nomultilib-openrc.txt'
        else:
            latest = 'latest-stage3-' + arch + '-hardened-openrc.txt'
    if stdlib == 'uclibc':
        assert False
        latest = 'latest-stage3-' + arch + '-uclibc-hardened.txt'
        eprint("uclibc wont compile efivars")
        quit(1)
    get_url = mirror + latest
    text = download_file(url=get_url, proxy_dict=proxy_dict)
    #r = requests.get(mirror + latest)
    eprint(text)
    autobuild_file_lines = text.split('\n')
    #r.close()
    path = ''
    for line in autobuild_file_lines:
        if 'stage3-' + arch in line:
            path = line.split(' ')[0]
            break
    #eprint('path:', path)
    assert 'stage3' in path
    url = mirror + path
    #eprint("url:", url)
    return url


def download_stage3(*,
                    destination_dir: Path,
                    stdlib: str,
                    multilib: bool,
                    arch: str,
                    proxy_dict: dict,
                    ):
    destination_dir = Path(destination_dir)
    url = get_stage3_url(proxy_dict=proxy_dict, stdlib=stdlib, multilib=multilib, arch=arch)
    ic(url)
    stage3_file = download_file(url=url, destination_dir=destination_dir, proxy_dict=proxy_dict)
    download_file(url=url + '.CONTENTS', destination_dir=destination_dir, proxy_dict=proxy_dict)
    download_file(url=url + '.DIGESTS', destination_dir=destination_dir, proxy_dict=proxy_dict)
    download_file(url=url + '.DIGESTS.asc', destination_dir=destination_dir, proxy_dict=proxy_dict)
    return Path(stage3_file)


def install_stage3(stdlib,
                   multilib: bool,
                   arch: str,
                   destination: Path,
                   distfiles_dir: Path,
                   vm: str,
                   vm_ram: int,
                   verbose: bool,
                   debug: bool,
                   ):

    destination = Path(destination)
    distfiles_dir = Path(distfiles_dir)
    ic(stdlib, multilib, arch, destination, vm)
    #os.chdir(destination)
    ic(destination)
    if not vm:
        assert path_is_mounted(destination, verbose=verbose, debug=debug,)
    with chdir(destination):
        ic(os.getcwd())
        assert os.getcwd() == str(destination)
        proxy_dict = construct_proxy_dict(verbose=verbose, debug=debug,)
        #url = get_stage3_url(stdlib=stdlib, multilib=multilib, arch=arch, proxy_dict=proxy_dict)
        #stage3_file = download_stage3(stdlib=stdlib, multilib=multilib, url=url, arch=arch, proxy_dict=proxy_dict)
        stage3_file = download_stage3(destination_dir=distfiles_dir, stdlib=stdlib, multilib=multilib, arch=arch, proxy_dict=proxy_dict)
        assert path_is_file(stage3_file)

        # this never worked
        #gpg = gnupg.GPG(verbose=True)
        #import_result = gpg.recv_keys('keyserver.ubuntu.com', '0x2D182910')
        #ceprint(import_result)

        ## this works sometimes, but now complaines abut no dirmngr
        #gpg_cmd = 'gpg --keyserver keyserver.ubuntu.com --recv-key 0x2D182910'
        ##if proxy:
        ##    keyserver_options = " --keyserver-options http_proxy=http://" + proxy
        ##    gpg_cmd += keyserver_options
        #run_command(gpg_cmd, verbose=True)

        ic(stage3_file)
        sh.gpg('--verify', '--verbose', stage3_file.as_posix() + '.DIGESTS.asc', _out=sys.stdout, _err=sys.stderr)

        #whirlpool = run_command("openssl dgst -r -whirlpool " + stage3_file.as_posix() + "| cut -d ' ' -f 1",
        #                        verbose=True).decode('utf8').strip()
        #try:
        #    run_command("/bin/grep " + whirlpool + ' ' + stage3_file.as_posix() + '.DIGESTS', verbose=True)
        #except CalledProcessError:
        #    ic('BAD WHIRPOOL HASH:', whirlpool)
        #    ic('For file:', stage3_file)
        #    ic('File is corrupt (most likely partially downloaded). Delete it and try again.')
        #    sys.exit(1)

        assert len(list(paths('.'))) == 1   # empty directory
        sh.tar('--xz', '-x', '-p', '-f', stage3_file.as_posix(), '-C', destination.as_posix(), _out=sys.stdout, _err=sys.stderr)

        #command = 'tar --xz -xpf ' + stage3_file.as_posix() + ' -C ' + destination.as_posix()
        #run_command(command, verbose=True)


@click.group()
@click.option('--verbose', is_flag=True)
@click.option('--debug', is_flag=True)
@click.pass_context
def cli(ctx,
        verbose: bool,
        debug: bool,
        ):

    null, end, verbose, debug = nevd(ctx=ctx,
                                     printn=False,
                                     ipython=False,
                                     verbose=verbose,
                                     debug=debug,)


@cli.command('get-stage3-url')
@click.option('--c-std-lib', is_flag=False, required=True, type=click.Choice(['glibc', 'musl', 'uclibc']),)
@click.option('--multilib', is_flag=True,)
@click.option('--proxy', is_flag=True)
@click.option('--verbose', is_flag=True)
@click.option('--debug', is_flag=True)
@add_options(click_arch_select)
@click.pass_context
def _get_stage3_url(ctx,
                    stdlib: str,
                    multilib: bool,
                    arch: str,
                    proxy: bool,
                    verbose: bool,
                    debug: bool,
                    ):
    if proxy:
        proxy_dict = construct_proxy_dict(verbose=verbose, debug=debug,)
    url = get_stage3_url(stdlib=stdlib, multilib=multilib, arch=arch, proxy_dict=proxy_dict)
    eprint(url)



@cli.command('download-stage3')
@click.option('--c-std-lib', is_flag=False, required=True, type=click.Choice(['glibc', 'musl', 'uclibc']))
@click.option('--multilib', is_flag=True, required=False)
@click.option('--proxy', is_flag=True)
@click.option('--verbose', is_flag=True)
@click.option('--debug', is_flag=True)
@add_options(click_arch_select)
@click.pass_context
def _download_stage3(ctx,
                     stdlib: str,
                     arch: str,
                     multilib: bool,
                     proxy: str,
                     verbose: bool,
                     debug: bool,
                     ):
    if proxy:
        proxy_dict = construct_proxy_dict(verbose=verbose, debug=debug,)
    destination_dir = Path('/var/db/repos/gentoo/distfiles/')
    download_stage3(destination_dir=destination_dir,
                    stdlib=stdlib,
                    multilib=multilib,
                    arch=arch,
                    proxy_dict=proxy_dict,)
