"""Parse OpenDRIVE .xodr → structured road/junction data with JSON cache."""

import json
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class LaneInfo:
    lane_id: int
    type: str  # driving, parking, shoulder, sidewalk, ...
    width: float  # from first <width> element's 'a' attribute
    travel_dir: str  # forward, backward, undirected


@dataclass
class RoadInfo:
    id: int
    name: str
    length: float
    predecessor_junction: Optional[int]  # None if predecessor is a road
    successor_junction: Optional[int]  # None if successor is a road
    predecessor_road: Optional[int]  # None if predecessor is a junction
    successor_road: Optional[int]  # None if successor is a road
    lanes: list  # list of LaneInfo dicts
    # XY of start (s=0) and end (s=length) from planView
    start_xy: list  # [x, y]
    end_xy: list  # [x, y]
    start_hdg: float  # heading at s=0
    end_hdg: float  # heading at s=length
    junction_id: int  # -1 for normal roads, junction id for connecting roads


@dataclass
class JunctionConnection:
    connection_id: int
    incoming_road: int
    connecting_road: int
    contact_point: str  # "start" or "end"
    lane_links: list  # list of {"from": int, "to": int}


@dataclass
class JunctionInfo:
    id: int
    name: str
    connections: list  # list of JunctionConnection dicts


class RoadNetworkDB:
    """Queryable database of OpenDRIVE road network data."""

    def __init__(self, xodr_path: str, cache_path: Optional[str] = None):
        self._xodr_path = os.path.abspath(xodr_path)
        if cache_path is None:
            cache_path = os.path.join(
                os.path.dirname(self._xodr_path),
                "road_network_cache.json",
            )
        self._cache_path = cache_path
        self._roads: dict[int, RoadInfo] = {}
        self._junctions: dict[int, JunctionInfo] = {}
        self._load()

    def _load(self):
        if self._cache_is_valid():
            self._load_from_cache()
        else:
            self._parse_xodr()
            self._save_cache()

    def _cache_is_valid(self) -> bool:
        if not os.path.exists(self._cache_path):
            return False
        cache_mtime = os.path.getmtime(self._cache_path)
        xodr_mtime = os.path.getmtime(self._xodr_path)
        return cache_mtime > xodr_mtime

    def _parse_xodr(self):
        tree = ET.parse(self._xodr_path)
        root = tree.getroot()

        for road_elem in root.findall("road"):
            ri = self._parse_road(road_elem)
            self._roads[ri.id] = ri

        for junc_elem in root.findall("junction"):
            ji = self._parse_junction(junc_elem)
            self._junctions[ji.id] = ji

    def _parse_road(self, elem) -> RoadInfo:
        road_id = int(elem.get("id"))
        name = elem.get("name", "")
        length = float(elem.get("length"))
        junction_id = int(elem.get("junction", "-1"))

        # Link: predecessor/successor
        pred_junc = None
        succ_junc = None
        pred_road = None
        succ_road = None
        link = elem.find("link")
        if link is not None:
            pred = link.find("predecessor")
            if pred is not None:
                if pred.get("elementType") == "junction":
                    pred_junc = int(pred.get("elementId"))
                else:
                    pred_road = int(pred.get("elementId"))
            succ = link.find("successor")
            if succ is not None:
                if succ.get("elementType") == "junction":
                    succ_junc = int(succ.get("elementId"))
                else:
                    succ_road = int(succ.get("elementId"))

        # Lanes
        lanes = []
        for lane_section in elem.findall(".//laneSection"):
            for side in ["left", "right"]:
                side_elem = lane_section.find(side)
                if side_elem is None:
                    continue
                for lane_elem in side_elem.findall("lane"):
                    lane_id = int(lane_elem.get("id"))
                    lane_type = lane_elem.get("type", "none")

                    # Width from first <width> element
                    width_elem = lane_elem.find("width")
                    width = float(width_elem.get("a", "0")) if width_elem is not None else 0.0

                    # Travel direction from userData/vectorLane
                    travel_dir = "undirected"
                    vl = lane_elem.find(".//vectorLane")
                    if vl is not None:
                        travel_dir = vl.get("travelDir", "undirected")

                    lanes.append(LaneInfo(
                        lane_id=lane_id,
                        type=lane_type,
                        width=width,
                        travel_dir=travel_dir,
                    ))

        # PlanView: extract start/end XY and heading
        start_xy = [0.0, 0.0]
        end_xy = [0.0, 0.0]
        start_hdg = 0.0
        end_hdg = 0.0
        plan_view = elem.find("planView")
        if plan_view is not None:
            geoms = plan_view.findall("geometry")
            if geoms:
                first = geoms[0]
                start_xy = [float(first.get("x", 0)), float(first.get("y", 0))]
                start_hdg = float(first.get("hdg", 0))
                last = geoms[-1]
                end_xy = [float(last.get("x", 0)), float(last.get("y", 0))]
                end_hdg = float(last.get("hdg", 0))

        return RoadInfo(
            id=road_id,
            name=name,
            length=length,
            predecessor_junction=pred_junc,
            successor_junction=succ_junc,
            predecessor_road=pred_road,
            successor_road=succ_road,
            lanes=[asdict(l) for l in lanes],
            start_xy=start_xy,
            end_xy=end_xy,
            start_hdg=start_hdg,
            end_hdg=end_hdg,
            junction_id=junction_id,
        )

    def _parse_junction(self, elem) -> JunctionInfo:
        junc_id = int(elem.get("id"))
        name = elem.get("name", "")
        connections = []
        for conn in elem.findall("connection"):
            lane_links = []
            for ll in conn.findall("laneLink"):
                lane_links.append({
                    "from": int(ll.get("from")),
                    "to": int(ll.get("to")),
                })
            connections.append(asdict(JunctionConnection(
                connection_id=int(conn.get("id")),
                incoming_road=int(conn.get("incomingRoad")),
                connecting_road=int(conn.get("connectingRoad")),
                contact_point=conn.get("contactPoint", ""),
                lane_links=lane_links,
            )))
        return JunctionInfo(id=junc_id, name=name, connections=connections)

    def _save_cache(self):
        data = {
            "roads": {str(k): asdict(v) for k, v in self._roads.items()},
            "junctions": {str(k): asdict(v) for k, v in self._junctions.items()},
        }
        with open(self._cache_path, "w") as f:
            json.dump(data, f, indent=2)

    def _load_from_cache(self):
        with open(self._cache_path) as f:
            data = json.load(f)
        for k, v in data["roads"].items():
            self._roads[int(k)] = RoadInfo(**v)
        for k, v in data["junctions"].items():
            v["connections"] = v.get("connections", [])
            self._junctions[int(k)] = JunctionInfo(**v)

    # ── Public API ────────────────────────────────────────────────────────

    def road(self, road_id: int) -> RoadInfo:
        if road_id not in self._roads:
            raise ValueError(f"Road {road_id} not found in road network")
        return self._roads[road_id]

    def junction(self, junction_id: int) -> JunctionInfo:
        if junction_id not in self._junctions:
            raise ValueError(f"Junction {junction_id} not found in road network")
        return self._junctions[junction_id]

    def driving_lanes(self, road_id: int) -> list[LaneInfo]:
        r = self.road(road_id)
        return [
            LaneInfo(**l) if isinstance(l, dict) else l
            for l in r.lanes
            if (l["type"] if isinstance(l, dict) else l.type) == "driving"
        ]

    def lane_info(self, road_id: int, lane_id: int) -> LaneInfo:
        r = self.road(road_id)
        for l in r.lanes:
            lid = l["lane_id"] if isinstance(l, dict) else l.lane_id
            if lid == lane_id:
                return LaneInfo(**l) if isinstance(l, dict) else l
        raise ValueError(f"Lane {lane_id} not found on road {road_id}")

    def validate_lane(self, road_id: int, lane_id: int, expected_type: str = "driving"):
        lane = self.lane_info(road_id, lane_id)
        if lane.type != expected_type:
            raise ValueError(
                f"Road {road_id} lane {lane_id} is '{lane.type}', expected '{expected_type}'"
            )

    def travel_direction_toward_junction(
        self, road_id: int, lane_id: int, junction_id: int
    ) -> bool:
        """Return True if the lane's travel direction moves toward the given junction.

        forward lanes travel s=0 → s=length (toward successor).
        backward lanes travel s=length → s=0 (toward predecessor).

        Raises if the lane doesn't travel toward that junction.
        """
        r = self.road(road_id)
        lane = self.lane_info(road_id, lane_id)

        if lane.travel_dir == "forward":
            # Forward goes toward successor
            if r.successor_junction == junction_id:
                return True
            raise ValueError(
                f"Road {road_id} lane {lane_id} (forward) goes toward successor "
                f"junction {r.successor_junction}, not {junction_id}"
            )
        elif lane.travel_dir == "backward":
            # Backward goes toward predecessor
            if r.predecessor_junction == junction_id:
                return True
            raise ValueError(
                f"Road {road_id} lane {lane_id} (backward) goes toward predecessor "
                f"junction {r.predecessor_junction}, not {junction_id}"
            )
        else:
            raise ValueError(
                f"Road {road_id} lane {lane_id} has undirected travel — "
                f"cannot determine direction toward junction {junction_id}"
            )

    def junction_end_s(self, road_id: int, junction_id: int) -> float:
        """Return the s-coordinate at the end of the road that touches the junction.

        If the junction is the predecessor, junction end is at s=0.
        If the junction is the successor, junction end is at s=road.length.
        """
        r = self.road(road_id)
        if r.predecessor_junction == junction_id:
            return 0.0
        elif r.successor_junction == junction_id:
            return r.length
        else:
            raise ValueError(
                f"Road {road_id} is not connected to junction {junction_id}. "
                f"Predecessor={r.predecessor_junction}, successor={r.successor_junction}"
            )

    def roads_at_junction(self, junction_id: int) -> list[int]:
        """Return list of incoming road IDs at a junction."""
        j = self.junction(junction_id)
        return list(set(c["incoming_road"] for c in j.connections))

    def all_road_ids(self) -> list[int]:
        return sorted(self._roads.keys())

    def all_junction_ids(self) -> list[int]:
        return sorted(self._junctions.keys())
