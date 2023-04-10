# Virtual Machine Manager
This package provides a simple Virtual Machine Manager. Currently, this is accomplished
using a `fzf` interface from the terminal, but the intent is to provide both a terminal
mode and a GUI mode using `wofi` instead of `fzf` and `notify-send` in place of terminal
logging.

At its core, this tool is simply a `libvirt` client akin to something like `virt-manager`.
However, it adds some functionality I've been wanting that isn't available in `virt-manager`.

The biggest plus is that I can integrate this tool into my system very easily. I use SwayWM
and `wofi` as my launcher, so interacting with virtual machines through a `wofi`-based
interface not only looks nice, but also is very intuitive. Further, `virt-manager` (and to
a larger extent `libvirt`) does not support any concept of VM organization. I set out building
this tool so that I would have a native way to organize and label my VMs. Additionally, the
`virt-manager` client has no way to create a linked or copy-on-write clone, and simply copies
entire VM disk images during a clone. This is slow and expensive. I don't believe there is any
`libvirt` API to explicitly create linked clones, but I plan to support this for local `libvirt`
connects by creating a child QCOW2 disk image during the clone. This will not work remotely,
but will work just fine when running locally.

This tool accomplishes directory-like organization and labeling by using `libvirt` application-
specific metadata attached to VMs. Specifically, it adds a `vmm` element to the `metadata` of
`libvirt` domains, which contains the virtual directory path of the VM, and a list of labels.
The metadata structure looks like this:

``` xml
<vmm:vmm xmlns:vmm="http://calebstew.art/xmlns/vmm">
    <vmm:path>/symbolic/vm/organization/path</vmm:path>
    <vmm:label>arbitrary-label</vmm:label>
    <vmm:label>another-label</vmm:label>
</vmm:vmm>
```

It's worth noting that this directory-like virtual path is not related to any on-disk path. The
VM definition and disk images are managed fully by `libvirt`. The path stored here is purely
for organization and is only interpreted by `vmm`. With that in mind, moving VMs between
these "pseudo-paths" is instantaneous. It is simply modifying the VM metadata.

The metadata information will not be modified on any VM unless you modify it by adding tags or
moving the VM within the virtual directory structure. The tool will work seamlessly with VMs
which do not have this metadata.  The defaults for these fields is simply an empty tag list
and a path of `/`. This enables `vmm` to work in tandem with VMs created, managed or used
from other `libvirt` clients while still providing an intuitive interface for interacting with VMs.
For existing VMs, the default empty values will be loaded and no modifications will be made
until requested.

Currently, `vmm` supports the following:
- Organize VMs in a directory-like structure, and browse those VMs
- Add/remove arbitrary tags on VMs
- Browse VMs by tag
- Start/Shutdown/Force Shutdown VMs
- Create Managed Saves (i.e. "Save State")
- Restore Managed Saves (i.e. "Restore"
- Restore to Snapshots

Planned Features:
- Create VMs (by invoking `virt-manager --show-domain-creator`).
- Create Snapshots
- Clone VMs (including Linked/Copy-on-Write clones)
