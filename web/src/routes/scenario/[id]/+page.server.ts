import { error } from '@sveltejs/kit';
import { loadScenarioById } from '$lib/server/load-scenarios';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = ({ params }) => {
	const id = parseInt(params.id, 10);
	const scenario = loadScenarioById(id);

	if (!scenario) {
		error(404, { message: `Scenario ${params.id} not found` });
	}

	return { scenario };
};
