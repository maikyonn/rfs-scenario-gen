from .s01_red_light_tbone import S01RedLightTBone
from .s02_rearend_chain import S02RearEndChain
from .s03_left_turn_motorcycle import S03LeftTurnMotorcycle
from .s04_parking_backing import S04ParkingBacking
from .s05_pedestrian_crosswalk import S05PedestrianCrosswalk
from .s06_sideswipe_lane_change import S06SideswipeLaneChange
from .s07_headon_wrong_way import S07HeadOnWrongWay
from .s08_cyclist_dooring import S08CyclistDooring
from .s09_stop_sign_rollthrough import S09StopSignRollthrough
from .s10_rearend_obstacle import S10RearEndObstacle

ALL_BUILDERS = [
    S01RedLightTBone,
    S02RearEndChain,
    S03LeftTurnMotorcycle,
    S04ParkingBacking,
    S05PedestrianCrosswalk,
    S06SideswipeLaneChange,
    S07HeadOnWrongWay,
    S08CyclistDooring,
    S09StopSignRollthrough,
    S10RearEndObstacle,
]
