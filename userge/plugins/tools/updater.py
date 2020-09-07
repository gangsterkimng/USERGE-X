# Copyright (C) 2020 by UsergeTeam@Github, < https://github.com/UsergeTeam >.
#
# This file is part of < https://github.com/UsergeTeam/Userge > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/uaudith/Userge/blob/master/LICENSE >
#
# All rights reserved.

import asyncio
from time import time

from git import Repo
from git.exc import GitCommandError

from userge import userge, Message, Config, pool

LOG = userge.getLogger(__name__)
CHANNEL = userge.getCLogger(__name__)
repo = Repo()

@userge.on_cmd("update", about={
    'header': "Check Updates or Update USERGE-X",
    'flags': {
        '-pull': "pull updates",
        '-push': "push updates to heroku",
        '-branch': "e.g -alpha, -beta etc. If not given default is -alpha"},
    'usage': "{tr}update : check updates from default branch\n"
             "{tr}update -[branch_name] : check updates from any branch\n"
             "add -pull if you want to pull updates\n"
             "add -push if you want to push updates to heroku",
    'examples': "{tr}update -pull -push"}, del_pre=True, allow_channels=False)
async def check_update(message: Message):
    """ check or do updates """
    await message.edit("`Checking for updates, please wait....`")
    try:
        repo.remote(Config.UPSTREAM_REMOTE).fetch()
    except GitCommandError as error:
        await message.err(error, del_in=5)
        return
    flags = list(message.flags)
    pull_from_repo = False
    push_to_heroku = False
    branch = "alpha"
    if "pull" in flags:
        pull_from_repo = True
        flags.remove("pull")
    if "push" in flags:
        push_to_heroku = True
        flags.remove("push")
    if len(flags) == 1:
        branch = flags[0]
    if branch not in repo.branches:
        await message.err(f'invalid branch name : {branch}')
        return
    out = ''
    try:
        for i in repo.iter_commits(f'HEAD..{Config.UPSTREAM_REMOTE}/{branch}'):
            out += (f"🔨 **#{i.count()}** : "
                    f"[{i.summary}]({Config.UPSTREAM_REPO.rstrip('/')}/commit/{i}) "
                    f"👷 __{i.author}__\n\n")
    except GitCommandError as error:
        await message.err(error, del_in=5)
        return
    if out:
        if pull_from_repo:
            await message.edit(f'`New update found for [{branch}], Now pulling...`')
            await asyncio.sleep(1)
            repo.git.checkout(branch, force=True)
            repo.git.reset('--hard', branch)
            repo.git.pull(Config.UPSTREAM_REMOTE, branch, force=True)
            await CHANNEL.log(f"**PULLED update from [{branch}]:\n\n📄 CHANGELOG 📄**\n\n{out}")
        elif not push_to_heroku:
            changelog_str = f'**New UPDATE available for [{branch}]:\n\n📄 CHANGELOG 📄**\n\n'
            await message.edit_or_send_as_file(changelog_str + out, disable_web_page_preview=True)
            return
    elif not push_to_heroku:
        if pull_from_repo:
            active = repo.active_branch.name
            await message.edit(
                f'`Moving HEAD from [{active}] >>> [{branch}] ...`', parse_mode='md')
            await asyncio.sleep(1)
            repo.git.checkout(branch, force=True)
            repo.git.reset('--hard', branch)
            await CHANNEL.log(f"`Moved HEAD from [{active}] >>> [{branch}] !`")
            await message.edit('`Now restarting... Wait for a while!`', del_in=3)
            asyncio.get_event_loop().create_task(userge.restart())
        else:
            await message.edit(f'**USERGE-X is up-to-date with [{branch}]**', del_in=5)
        return
    if not push_to_heroku:
        await message.edit(
            '**USERGE-X Successfully Updated!**\n'
            '`Now restarting... Wait for a while!`', del_in=3)
        asyncio.get_event_loop().create_task(userge.restart(True))
        return
    if not Config.HEROKU_APP:
        await message.err("HEROKU APP : could not be found !")
        return
    sent = await message.edit(
        f'`Now pushing updates from [{branch}] to heroku...\n'
        'this will take upto 5 min`\n\n'
        f'* **Restart** after 5 min using `{Config.CMD_TRIGGER}restart -h`\n\n'
        '* After restarted successfully, check updates again :)')
    try:
        await _push_to_heroku(sent, branch)
    except GitCommandError as g_e:
        LOG.exception(g_e)
        await sent.err(f"{g_e}, {Config.CMD_TRIGGER}restart -h and try again!")
    else:
        await sent.edit(f"**HEROKU APP : {Config.HEROKU_APP.name} is up-to-date with [{branch}]**")


@pool.run_in_thread
def _push_to_heroku(sent: Message, branch: str) -> None:
    start_time = time()
    edited = False

    def progress(op_code, cur_count, max_count=None, message=''):
        nonlocal start_time, edited
        prog = f"**code:** `{op_code}` **cur:** `{cur_count}`"
        if max_count:
            prog += f" **max:** `{max_count}`"
        if message:
            prog += f" || `{message}`"
        LOG.debug(prog)
        now = time()
        if not edited or (now - start_time) > 3 or message:
            edited = True
            start_time = now
            try:
                loop.run_until_complete(sent.try_to_edit(f"{cur_msg}\n\n{prog}"))
            except TypeError:
                pass
    if not "heroku" in repo.remotes:
        remote = repo.create_remote("heroku", Config.HEROKU_GIT_URL)
    cur_msg = sent.text.html
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        Repo().remote("heroku").push(refspec=f'{branch}:master',
                                     progress=progress,
                                     force=True)
    finally:
        loop.close()
