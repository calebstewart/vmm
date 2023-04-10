from typing import List
from pathlib import Path
from xml.etree import ElementTree

import typer
import libvirt
from loguru import logger

from vmm.wofi import wofi, Mode, WofiError
from vmm.config import Config
from vmm.model import Domain
from vmm.menu import Item, Fzf

app = typer.Typer()
config = Config()


@app.command()
def main():
    """Open the VM Manager Menu"""

    # Silence libvirt
    # NOTE: see https://stackoverflow.com/questions/45541725/avoiding-console-prints-by-libvirt-qemu-python-apis#answer-45543887
    libvirt.registerErrorHandler(lambda _, __: None, ctx=None)

    try:
        conn = libvirt.open(config.connect_uri)
    except libvirt.libvirtError as exc:
        logger.error("failed to connect to libvirt: {exc}", exc=str(exc))
        return

    domains: List[Domain] = []

    domainNames = conn.listDefinedDomains()
    for domain in domainNames:
        domInfo = conn.lookupByName(domain)
        domains.append(Domain.from_virdomain(domInfo))

    main_menu(conn, domains)


def main_menu(conn: libvirt.virConnect, domains: List[Domain]):
    """Show the main menu"""

    CREATE_VM = Item("\u002b  Create Virtual Machine")
    BROWSE_ALL = Item("\uf233  Browse All")
    BROWSE_BY_PATH = Item("\uf07b  Browse VM Folders")
    BROWSE_BY_LABEL = Item("\uf02b  Browse VM Labels")

    while True:
        selected = Fzf.prompt("> ", [CREATE_VM, BROWSE_BY_PATH, BROWSE_BY_LABEL])
        if selected is None:
            logger.warning("aborted")
            return
        elif selected == CREATE_VM:
            logger.info("Creating a new VM")
        elif selected == BROWSE_BY_PATH:
            browse_by_path(conn, domains, Path("/"))
        elif selected == BROWSE_BY_LABEL:
            browse_by_label(conn, domains)
        elif selected == BROWSE_ALL:
            browse_all(conn, domains)


class FolderItem(Item):
    def __init__(self, path: Path):
        super().__init__(f"\uf07b  {path}", bold=True)
        self.path = path


class DomainItem(Item):
    def __init__(self, domain: Domain):
        super().__init__(f"\uf233  {domain.name}")
        self.domain = domain


class LabelItem(Item):
    def __init__(self, label: str):
        super().__init__(f"\uf02b  {label}")
        self.label = label


def browse_by_path(conn: libvirt.virConnect, domains: List[Domain], path: Path):
    """Browse VMs by their path"""

    while True:
        children = set()
        for domain in domains:
            if path != domain.metadata.path and domain.metadata.path.is_relative_to(
                path
            ):
                children.add(str(domain.metadata.path.relative_to(path)))

        options: List[Item] = sorted(
            [FolderItem(Path(child)) for child in children], key=lambda x: x.path
        )
        options.extend(
            sorted(
                [
                    DomainItem(domain)
                    for domain in domains
                    if domain.metadata.path == path
                ],
                key=lambda x: x.domain.name,
            )
        )

        selected = Fzf.prompt(f"browse[{path}]> ", options)
        if selected == None:
            return
        elif isinstance(selected, FolderItem):
            browse_by_path(conn, domains, path / selected.path)
        elif isinstance(selected, DomainItem):
            interact_with_vm(conn, domains, selected.domain)


def browse_by_label(conn: libvirt.virConnect, domains: List[Domain]):
    """Browse VMs by tag"""

    labels = set()
    for domain in domains:
        labels |= set(domain.metadata.labels)

    while True:
        labelItem: LabelItem | None = Fzf.prompt(
            "browse[by-label]> ", [LabelItem(label) for label in labels]
        )
        if labelItem is None:
            return

        domainItem = Fzf.prompt(
            f"browse[by-label={labelItem.label}]",
            [
                DomainItem(domain)
                for domain in domains
                if labelItem.label in domain.metadata.labels
            ],
        )
        if domainItem is None:
            continue

        interact_with_vm(conn, domains, domainItem.domain)


def interact_with_vm(conn: libvirt.virConnect, domains: List[Domain], domain: Domain):
    """Interact with the selected domain"""

    ACTION_START = Item("\uf04b  Start")
    ACTION_SHUTDOWN = Item("\uf011  Shutdown")
    ACTION_FORCE_OFF = Item("\uf1e6  Force Off")
    ACTION_SAVE_STATE = Item("\uf0c7  Save State")
    ACTION_RESTORE_STATE = Item("\uf04b  Restore Save State")
    ACTION_REMOVE_STATE = Item("\uf05e  Remove Save State")
    ACTION_CLEAN_START = Item("\uf021  Remove Save State and Start")
    ACTION_LINKED_CLONE = Item("\uf24d  Clone (Linked)")
    ACTION_HEAVY_CLONE = Item("\uf24d  Clone (Heavy)")
    ACTION_SNAPSHOT = Item("\uf030  Take a Snapshot")
    ACTION_RESTORE_SNAPSHOT = Item("\uf017  Restore Snapshot")
    ACTION_MOVE = Item("\uf07b  Move To...")
    ACTION_ADD_LABEL = Item("\uf02b  Add Label")
    ACTION_REMOVE_LABEL = Item("\uf02b  Remove Label")

    while True:

        try:
            domInfo = domain.lookup(conn)
        except libvirt.libvirtError as exc:
            logger.error("failed to lookup domain: {exc}", exc=str(exc))
            return

        actions = []

        if domInfo.isActive():
            actions.extend([ACTION_SHUTDOWN, ACTION_FORCE_OFF, ACTION_SAVE_STATE])
        elif domInfo.hasManagedSaveImage():
            actions.extend(
                [ACTION_RESTORE_STATE, ACTION_REMOVE_STATE, ACTION_CLEAN_START]
            )
        else:
            actions.extend([ACTION_START])

        actions.extend(
            [
                ACTION_LINKED_CLONE,
                ACTION_HEAVY_CLONE,
                ACTION_SNAPSHOT,
                ACTION_RESTORE_SNAPSHOT,
                ACTION_MOVE,
                ACTION_ADD_LABEL,
                ACTION_REMOVE_LABEL,
            ]
        )

        selected = Fzf.prompt(f"domain[{domain.path}]> ", actions)

        if selected is None:
            return
        elif selected == ACTION_START or selected == ACTION_RESTORE_STATE:
            domInfo.create()
            Fzf.notify("starting domain '{domain}'", domain=domain.name)
        elif selected == ACTION_CLEAN_START:
            domInfo.createWithFlags(libvirt.VIR_DOMAIN_START_FORCE_BOOT)
            Fzf.notify("clean starting domain '{domain}'", domain=domain.name)
        elif selected == ACTION_SHUTDOWN:
            domInfo.shutdown()
            Fzf.notify("requesting domain '{domain}' shutdown", domain=domain.name)
        elif selected == ACTION_FORCE_OFF:
            domInfo.destroy()
            Fzf.notify("forcing domain '{domain}' off", domain=domain.name)
        elif selected == ACTION_SAVE_STATE:
            domInfo.managedSave()
            Fzf.notify("saving domain '{domain}' state", domain=domain.name)
        elif selected == ACTION_REMOVE_STATE:
            domInfo.managedSaveRemove()
            Fzf.notify("removed domain '{domain}' saved state", domain=domain.name)
        elif selected == ACTION_MOVE:
            do_domain_move(conn, domains, domain)
        elif selected == ACTION_ADD_LABEL:
            do_domain_add_label(conn, domains, domain)
        elif selected == ACTION_REMOVE_LABEL:
            do_domain_remove_label(conn, domain)
        elif selected == ACTION_RESTORE_SNAPSHOT:
            do_domain_revert(conn, domain)


class SnapshotItem(Item):
    def __init__(self, snapshot: libvirt.virDomainSnapshot):
        super().__init__(f"\uf030  {snapshot.getName()}")
        self.snapshot = snapshot


def do_domain_revert(conn: libvirt.virConnect, domain: Domain):
    """Revert a domain to one of the previous snapshots"""

    info = domain.lookup(conn)
    snapshotNames = info.listAllSnapshots()

    item = Fzf.prompt(
        f"revert-to-snapshot[{domain.path}]> ",
        [SnapshotItem(snap) for snap in snapshotNames],
    )
    if item is None:
        return

    info.revertToSnapshot(item.snapshot)

    Fzf.notify(
        "reverted domain '{domain}' to '{snapshot}'",
        domain=domain.name,
        snapshot=item.snapshot.getName(),
    )


def do_domain_move(conn: libvirt.virConnect, domains: List[Domain], domain: Domain):
    """Move the domain path tag"""

    options = [Item("\u002b  New Folder")]
    options.extend(
        sorted(
            [FolderItem(path) for path in set([d.metadata.path for d in domains])],
            key=lambda item: item.path,
        )
    )

    item = Fzf.prompt(f"move-domain[{domain.path}]> ", options=options)
    if item is None:
        return
    elif isinstance(item, FolderItem):
        new_path = item.path
    else:
        value = Fzf.ask(f"new-folder[{domain.name}]> ", options=[Item("")])
        if value is None:
            return
        else:
            new_path = Path(value)

    domain.metadata.path = new_path
    domain.update(conn)

    Fzf.notify(
        "moved domain '{domain}' to '{new_dir}'", domain=domain.name, new_dir=new_path
    )


def do_domain_add_label(
    conn: libvirt.virConnect, domains: List[Domain], domain: Domain
):
    """Add a new label to a domain"""

    # Collect all labels
    labels = set()
    for d in domains:
        labels |= set(d.metadata.labels)

    new_label = Fzf.ask(
        f"add-domain-label[{domain.path}]> ",
        options=[Item(str(label)) for label in labels],
    )

    if new_label is None:
        return

    domain.metadata.labels = list(set(domain.metadata.labels) | {new_label})
    domain.update(conn)

    Fzf.notify(
        "adding label '{new_label}' to '{domain}'",
        new_label=new_label,
        domain=domain.name,
    )


def do_domain_remove_label(conn: libvirt.virConnect, domain: Domain):
    """Remove a label from a domain"""

    if not domain.metadata.labels:
        return

    labelItem = Fzf.prompt(
        f"remove-label[{domain.path}]> ",
        options=[Item(str(l)) for l in set(domain.metadata.labels)],
    )
    if labelItem is None:
        return
    else:
        label = labelItem.text

    domain.metadata.labels = [l for l in set(domain.metadata.labels) if l != label]
    domain.update(conn)

    Fzf.notify(
        "removed label '{label}' from '{domain}'", label=label, domain=domain.name
    )


if __name__ == "__main__":
    app()
