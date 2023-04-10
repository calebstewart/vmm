from typing import List
from pathlib import Path
import uuid

from pydantic_xml import BaseXmlModel, element
from pydantic import BaseModel
import libvirt

NSMAP = {"vmmgr": "http://calebstew.art/vmmgr"}
NAMESPACE = "http://calebstew.art/xmlns/vmmgr"


class ManagerMetadata(BaseXmlModel, tag="vmmgr"):
    path: Path = element(default=Path("/"))
    labels: List[str] = element(tag="label", default=[])


class Domain(BaseModel):
    """Base domain management object"""

    name: str
    id: str
    uuid: uuid.UUID
    metadata: ManagerMetadata

    @property
    def path(self) -> Path:
        return self.metadata.path / self.name

    def lookup(self, conn: libvirt.virConnect):
        return conn.lookupByUUID(self.uuid.bytes)

    def update(self, conn: libvirt.virConnect):
        """Update the domain with saved metadata information"""

        dom = self.lookup(conn)
        dom.setMetadata(
            libvirt.VIR_DOMAIN_METADATA_ELEMENT,
            self.metadata.to_xml(encoding="utf-8").decode("utf-8"),
            "vmmgr",
            NAMESPACE,
        )

    @classmethod
    def from_virdomain(cls, dom: libvirt.virDomain) -> "Domain":
        """Construct a domain object from a libvirt.virDomain"""

        name = dom.name()
        id = dom.ID()
        uuid = dom.UUID()

        try:
            raw_metadata = dom.metadata(
                libvirt.VIR_DOMAIN_METADATA_ELEMENT,
                NAMESPACE,
            )
            if not raw_metadata:
                metadata = ManagerMetadata()
            else:
                metadata = ManagerMetadata.from_xml(raw_metadata)
        except libvirt.libvirtError as e:
            metadata = ManagerMetadata()

        return Domain(name=name, id=id, uuid=uuid, metadata=metadata)
