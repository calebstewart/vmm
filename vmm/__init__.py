from typing import List
from pathlib import Path
from xml.etree import ElementTree
import tempfile
import subprocess
import os
import shutil
import sys
import uuid

import typer
import libvirt
from rich.console import Console
from loguru import logger

from vmm.wofi import wofi, Mode, WofiError
from vmm.config import Config
from vmm.model import Domain
from vmm.menu import Item, Fzf

app = typer.Typer()
config = Config()
console = Console()


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


class SnapshotItem(Item):
    def __init__(self, snapshot: libvirt.virDomainSnapshot):
        super().__init__(f"\uf030  {snapshot.getName()}")
        self.snapshot = snapshot


@app.command()
def main(exit: bool = False):
    """Open the VM Manager Menu"""

    # Silence libvirt
    # NOTE: see https://stackoverflow.com/questions/45541725/avoiding-console-prints-by-libvirt-qemu-python-apis#answer-45543887
    libvirt.registerErrorHandler(lambda _, __: None, ctx=None)

    try:
        conn = libvirt.open(config.connect_uri)
    except libvirt.libvirtError as exc:
        logger.error("failed to connect to libvirt: {exc}", exc=str(exc))
        return

    domains: List[Domain] = [
        Domain.from_virdomain(domInfo) for domInfo in conn.listAllDomains()
    ]

    config.exit_after_action = exit

    main_menu(conn, domains)


def main_menu(conn: libvirt.virConnect, domains: List[Domain]):
    """Show the main menu"""

    CREATE_VM = Item("\u002b  Create Virtual Machine")
    BROWSE_ALL = Item("\uf0ac  Browse All")
    BROWSE_BY_PATH = Item("\uf07b  Browse VM Folders")
    BROWSE_BY_LABEL = Item("\uf02b  Browse VM Labels")

    while True:
        options = [CREATE_VM, BROWSE_ALL, BROWSE_BY_PATH, BROWSE_BY_LABEL]

        # Add any active domains to the list
        for domain in domains:
            if domain.lookup(conn).isActive():
                options.append(DomainItem(domain))

        selected = Fzf.prompt("> ", options)
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
        elif isinstance(selected, DomainItem):
            interact_with_vm(conn, domains, selected.domain)


def browse_all(conn: libvirt.virConnect, domains: List[Domain]):
    """Browse all VMs as one long list"""

    while True:
        options: List[Item] = sorted(
            [DomainItem(domain) for domain in domains],
            key=lambda item: item.domain.name,
        )

        item = Fzf.prompt(f"browse[all]> ", options)
        if item is None:
            return
        elif isinstance(item, DomainItem):
            interact_with_vm(conn, domains, item.domain)


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
    ACTION_EDIT_XML = Item("\uf044  Edit XML")
    ACTION_OPEN = Item("\uf26c  Open Viewer")
    ACTION_LOOKING_GLASS = Item("\uf26c  Open Looking Glass")

    while True:

        try:
            domInfo = domain.lookup(conn)
        except libvirt.libvirtError as exc:
            logger.error("failed to lookup domain: {exc}", exc=str(exc))
            return

        actions = []

        if domInfo.isActive():
            actions.extend(
                [
                    ACTION_OPEN,
                    ACTION_LOOKING_GLASS,
                    ACTION_SHUTDOWN,
                    ACTION_FORCE_OFF,
                    ACTION_SAVE_STATE,
                ]
            )
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
                ACTION_EDIT_XML,
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
        elif selected == ACTION_EDIT_XML:
            do_domain_edit(conn, domain)
        elif selected == ACTION_OPEN:
            subprocess.Popen(
                [
                    "setsid",
                    "virt-viewer",
                    "--connect",
                    config.connect_uri,
                    "--auto-resize",
                    "always",
                    "--cursor",
                    "auto",
                    "--reconnect",
                    "--wait",
                    "--uuid",
                    "--shared",
                    str(domain.uuid),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            Fzf.notify("Starting virt-viewer for domain '{domain}'", domain=domain.path)
            sys.exit(0)
        elif selected == ACTION_LOOKING_GLASS:
            subprocess.Popen(
                [
                    "setsid",
                    "looking-glass-client",
                    str(domain.uuid),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            Fzf.notify(
                "Starting looking-glass for domain '{domain}'", domain=domain.path
            )
            sys.exit(0)
        elif selected == ACTION_LINKED_CLONE:
            do_domain_clone(conn, domains, domain, copy_on_write=True)
        elif selected == ACTION_HEAVY_CLONE:
            do_domain_clone(conn, domains, domain, copy_on_write=False)

        if config.exit_after_action:
            sys.exit(0)


def do_domain_clone(
    conn: libvirt.virConnect, domains: List[Domain], domain: Domain, copy_on_write: bool
):
    """Create a linked clone of the specified domain"""

    # Lookup the domain information
    domInfo = domain.lookup(conn)
    root = ElementTree.fromstring(domInfo.XMLDesc())

    # Ask for the new VM name
    new_name = Fzf.ask(f"domain-linked-clone[{domain.path}] clone name> ")
    if new_name is None:
        return

    new_uuid = uuid.uuid4()

    # Update the name field in the domain XMl
    name = root.find("./name")
    if name is None:
        name = ElementTree.SubElement(root, "name")
    name.text = new_name

    # Generate a new domain UUID
    uuidElem = root.find("./uuid")
    if uuidElem is None:
        uuidElem = ElementTree.SubElement(root, "uuid")
    uuidElem.text = str(new_uuid)

    logger.debug(
        "building domain specification for {name} ({uuid})",
        name=new_name,
        uuid=new_uuid,
    )

    for disk in root.findall("devices/disk"):
        targetElem = disk.find("./target")
        if targetElem is None:
            logger.debug(
                "  {domain}: ignoring disk with no target element", domain=domain.name
            )
            continue

        disk_name = targetElem.attrib["dev"]

        if disk.find("readonly") is not None:
            logger.debug(
                "  {domain}: {disk}: leaving read-only disk unchanged",
                domain=new_name,
                disk=disk_name,
            )
            continue

        with console.status(f"cloning {disk_name}"):
            do_domain_disk_clone(conn, domain, new_name, disk_name, disk, copy_on_write)

    # Define the new cloned VM
    cloneInfo = conn.defineXML(
        ElementTree.tostring(root, encoding="unicode", method="xml")
    )

    domains.append(Domain.from_virdomain(cloneInfo))


def do_domain_disk_clone(
    conn: libvirt.virConnect,
    domain: Domain,
    cloneName: str,
    disk_name: str,
    disk: ElementTree.Element,
    copy_on_write: bool,
):
    """Clone an individual disk from the given domain. The disk element is assumed to be from
    the in-progress domain clone, and will be updated to refer to the new cloned disk."""

    logger.debug(
        "  {domain}: {disk}: cloning read-write disk",
        domain=cloneName,
        disk=disk_name,
    )

    sourceElem = disk.find("./source")
    if sourceElem is None:
        logger.debug(
            "  {domain}: {disk}: skipping because no source element found",
            domain=cloneName,
            disk=disk_name,
        )
        return

    source_path = sourceElem.attrib["file"]

    backingVolume = conn.storageVolLookupByPath(source_path)
    if backingVolume is None:
        logger.error(
            "  {domain}: {disk}: could not find backing storage volume",
            domain=cloneName,
            disk=disk_name,
        )
        return

    # Look up the backing storage pool (place the clone in the same pool)
    backingPool = backingVolume.storagePoolLookupByVolume()

    # Parse the backing volume to extract the volume and target types
    backingVolumeElem = ElementTree.fromstring(backingVolume.XMLDesc())
    volumeType = backingVolumeElem.attrib["type"]

    # Lookup the target type
    backingVolumeTargetFormat = backingVolumeElem.find("./target/format")
    if backingVolumeTargetFormat is None:
        targetFormat = None
    else:
        targetFormat = backingVolumeTargetFormat.attrib["type"]

    # Create the new volume XML tree and add our clone name
    newVolumeTree = ElementTree.Element("volume", type=volumeType)
    ElementTree.SubElement(newVolumeTree, "name").text = f"{cloneName}.qcow2"

    # Set the target format if we know it
    if targetFormat is not None:
        newVolumeTarget = ElementTree.SubElement(newVolumeTree, "target")
        ElementTree.SubElement(newVolumeTarget, "format", type=targetFormat)

    # Use a backing store for qcow2 images
    # This means that for non-qcow2 images, we default to a raw clone
    if targetFormat == "qcow2" and copy_on_write:
        backingStore = ElementTree.SubElement(newVolumeTree, "backingStore")
        ElementTree.SubElement(backingStore, "path").text = source_path
        ElementTree.SubElement(backingStore, "format", type=targetFormat)

        # Create the new clone using a backing store
        newVolume = backingPool.createXML(
            ElementTree.tostring(newVolumeTree, encoding="unicode", method="xml")
        )

        logger.debug(
            "  {domain}: {disk}: created backed volume clone: {volume}",
            domain=cloneName,
            disk=disk_name,
            volume=newVolume.name(),
        )
    else:
        newVolume = backingPool.createXMLFrom(
            ElementTree.tostring(newVolumeTree, encoding="unicode", method="xml"),
            backingVolume,
        )

        logger.debug(
            "  {domain}: {disk}: copied existing volume: {volume}",
            domain=cloneName,
            disk=disk_name,
            volume=newVolume.name(),
        )

    # Retrive the disk source element
    diskSource = disk.find("./source")
    if diskSource is None:
        diskSource = ElementTree.SubElement(disk, "source")

    # Update the source to point to our new volume
    diskSource.attrib["file"] = newVolume.path()

    return newVolume.path()


def do_domain_edit(conn: libvirt.virConnect, domain: Domain):
    """Edit a Domain XML"""

    interactive = sys.stdout.isatty() and sys.stdin.isatty()
    if not interactive:
        command = config.noninteractive_editor
        editor_kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    else:
        editor = shutil.which(os.environ.get("EDITOR", "vim"))
        if editor is None:
            Fzf.notify("could not find suitable editor")
            return
        command = [editor]
        editor_kwargs = {}

    with tempfile.NamedTemporaryFile("w+", suffix=".xml") as filp:

        while True:
            domInfo = domain.lookup(conn)
            original = domInfo.XMLDesc()
            filp.seek(0)
            filp.truncate(0)
            filp.write(original)
            filp.flush()

            try:
                subprocess.run([*command, filp.name], check=True, **editor_kwargs)
            except subprocess.CalledProcessError as exc:
                Fzf.notify("editor had non-zero exit status; aborting domain edit.")
                return

            try:
                subprocess.run(["virt-xml-validate", filp.name], check=True)
                filp.seek(0)

                new_xml = filp.read()
                if new_xml == original:
                    Fzf.notify("no changes for domain '{domain}'", domain=domain.path)
                else:
                    conn.defineXML(filp.read())
                    Fzf.notify("updated domain '{domain}'", domain=domain.path)
                break
            except subprocess.CalledProcessError as exc:
                Fzf.notify("invalid domain XML")
                input()


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
