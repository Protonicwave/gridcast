"""The 14 distribution network regions of Great Britain."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Region:
    """A region as named by the Carbon Intensity API and by the boundary file."""

    api_id: int
    name: str
    boundary_area: str


REGIONS = (
    Region(1, "North Scotland", "North Scotland"),
    Region(2, "South Scotland", "South and Central Scotland"),
    Region(3, "North West England", "North West England"),
    Region(4, "North East England", "North East England"),
    Region(5, "Yorkshire", "Yorkshire"),
    Region(6, "North Wales & Merseyside", "North Wales, Merseyside and Cheshire"),
    Region(7, "South Wales", "South Wales"),
    Region(8, "West Midlands", "West Midlands"),
    Region(9, "East Midlands", "East Midlands"),
    Region(10, "East England", "East England"),
    Region(11, "South West England", "South West England"),
    Region(12, "South England", "Southern England"),
    Region(13, "London", "London"),
    Region(14, "South East England", "South East England"),
)
