import { loadAllScenarios } from '$lib/server/load-scenarios';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = () => {
	const scenarios = loadAllScenarios();
	return { scenarios };
};
