import { readFileSync, readdirSync, existsSync } from 'fs';
import { join, resolve } from 'path';
import type { Scenario } from '$lib/data/scenarios';

const PROJECT_ROOT = resolve(process.cwd(), '..');

interface CrashSituation {
	id: number;
	pattern: string;
	description: string;
	entities: string[];
	speeds_mph: number[];
}

interface ConfigEntity {
	name: string;
	type: string;
}

interface ConfigInitAction {
	entity: string;
	road: number;
	lane: number;
	s: number;
	speed_mph: number;
}

interface ConfigRoute {
	entity: string;
	start_road: number;
	exit_road: number;
}

interface ScenarioConfig {
	situation_id: number;
	pattern: string;
	scenario_name: string;
	sim_time: number;
	entities: ConfigEntity[];
	init_actions: ConfigInitAction[];
	routes?: ConfigRoute[];
}

let cachedSituations: CrashSituation[] | null = null;

function loadSituations(): CrashSituation[] {
	if (cachedSituations) return cachedSituations;
	const path = join(PROJECT_ROOT, 'crash_situations.json');
	const data = JSON.parse(readFileSync(path, 'utf-8'));
	cachedSituations = data.situations;
	return cachedSituations!;
}

function loadConfig(id: number): ScenarioConfig | null {
	const path = join(PROJECT_ROOT, 'generator', 'configs', `situation_${String(id).padStart(3, '0')}.json`);
	if (!existsSync(path)) return null;
	return JSON.parse(readFileSync(path, 'utf-8'));
}

function findXoscFile(id: number): string | null {
	const outputDir = join(PROJECT_ROOT, 'generator', 'output');
	if (!existsSync(outputDir)) return null;
	const prefix = `cs${String(id).padStart(3, '0')}_`;
	const files = readdirSync(outputDir);
	const match = files.find((f) => f.startsWith(prefix) && f.endsWith('.xosc'));
	return match ?? null;
}

function findVideoFiles(id: number): { videoPath: string; thumbnailPath: string } {
	const renderDir = join(PROJECT_ROOT, 'render', 'output');
	if (!existsSync(renderDir)) return { videoPath: '', thumbnailPath: '' };

	const files = readdirSync(renderDir);

	// Check for cs### prefixed files first (new pipeline)
	const csPrefix = `cs${String(id).padStart(3, '0')}_`;
	const csVideo = files.find((f) => f.startsWith(csPrefix) && f.endsWith('.mp4'));
	if (csVideo) {
		const csThumb = files.find((f) => f.startsWith(csPrefix) && f.endsWith('.jpg'));
		return {
			videoPath: `/videos/${csVideo}`,
			thumbnailPath: csThumb ? `/videos/${csThumb}` : ''
		};
	}

	// Check for s## prefixed files (original 10 scenarios)
	const sPrefix = `s${String(id).padStart(2, '0')}_`;
	const sVideo = files.find((f) => f.startsWith(sPrefix) && f.endsWith('.mp4'));
	if (sVideo) {
		const sThumb = files.find((f) => f.startsWith(sPrefix) && f.endsWith('.jpg'));
		return {
			videoPath: `/videos/${sVideo}`,
			thumbnailPath: sThumb ? `/videos/${sThumb}` : ''
		};
	}

	return { videoPath: '', thumbnailPath: '' };
}

function extractRoads(config: ScenarioConfig): string {
	const roads = new Set<number>();
	for (const action of config.init_actions) {
		roads.add(action.road);
	}
	return [...roads].map((r) => `Road ${r}`).join(', ');
}

function extractJunction(config: ScenarioConfig): string {
	if (!config.routes || config.routes.length === 0) return 'None';
	// Junction scenarios have routes — we can't know the junction ID from config alone,
	// but we know the pattern tells us it's a junction scenario
	if (config.pattern === 'junction_tbone') {
		const roads = config.init_actions.map((a) => a.road);
		// Known junction mappings
		const junctionMap: Record<string, string> = {
			'52,44': 'Junction 323',
			'44,52': 'Junction 323',
			'19,44': 'Junction 323',
			'44,19': 'Junction 323',
			'28,39': 'Junction 199',
			'39,28': 'Junction 199',
			'28,54': 'Junction 199',
			'54,28': 'Junction 199',
			'40,24': 'Junction 103',
			'24,40': 'Junction 103'
		};
		const key = roads.slice(0, 2).join(',');
		return junctionMap[key] ?? 'Junction';
	}
	return 'None';
}

function formatSpeeds(speeds: number[]): string {
	const unique = [...new Set(speeds.filter((s) => s > 0))];
	if (unique.length === 0) return '0 mph';
	return unique.join(' / ') + ' mph';
}

function buildScenario(situation: CrashSituation, config: ScenarioConfig | null, xoscFile: string | null): Scenario {
	const id = situation.id;
	const idStr = String(id).padStart(3, '0');

	// Try to create a readable name from config scenario_name or situation description
	let name: string;
	if (config) {
		name = config.scenario_name
			.replace(/_/g, ' ')
			.replace(/([a-z])([A-Z])/g, '$1 $2');
	} else {
		name = `Scenario ${id}`;
	}

	const roads = config ? extractRoads(config) : 'Unknown';
	const junction = config ? extractJunction(config) : 'Unknown';
	const duration = config ? `${config.sim_time}s` : '15s';

	const { videoPath, thumbnailPath } = findVideoFiles(id);

	return {
		id,
		name,
		pattern: situation.pattern,
		description: situation.description,
		roads,
		junction,
		speeds: formatSpeeds(situation.speeds_mph),
		entities: situation.entities,
		duration,
		videoPath,
		thumbnailPath,
		xoscPath: xoscFile ? `/xosc/${xoscFile}` : ''
	};
}

export function loadAllScenarios(): Scenario[] {
	const situations = loadSituations();
	return situations.map((sit) => {
		const config = loadConfig(sit.id);
		const xoscFile = findXoscFile(sit.id);
		return buildScenario(sit, config, xoscFile);
	});
}

export function loadScenarioById(id: number): Scenario | null {
	const situations = loadSituations();
	const situation = situations.find((s) => s.id === id);
	if (!situation) return null;
	const config = loadConfig(id);
	const xoscFile = findXoscFile(id);
	return buildScenario(situation, config, xoscFile);
}
