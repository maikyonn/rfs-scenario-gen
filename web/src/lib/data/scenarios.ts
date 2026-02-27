export interface Scenario {
	id: number;
	name: string;
	pattern: string;
	description: string;
	roads: string;
	junction: string;
	speeds: string;
	entities: string[];
	duration: string;
	videoPath: string;
	thumbnailPath: string;
	xoscPath: string;
}

export const patternLabels: Record<string, string> = {
	junction_tbone: 'Junction T-Bone',
	rear_end: 'Rear End',
	head_on: 'Head On',
	sideswipe: 'Sideswipe',
	pedestrian_crossing: 'Pedestrian',
	dooring: 'Dooring',
	parking_backing: 'Parking'
};

export const patternColors: Record<string, string> = {
	junction_tbone: '#f87171',
	rear_end: '#fb923c',
	head_on: '#facc15',
	sideswipe: '#4ade80',
	pedestrian_crossing: '#60a5fa',
	dooring: '#c084fc',
	parking_backing: '#f472b6'
};
