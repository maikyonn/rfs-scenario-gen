<script lang="ts">
	import { patternLabels, patternColors } from '$lib/data/scenarios';
	import ScenarioCard from '$lib/components/ScenarioCard.svelte';

	let { data } = $props();

	let search = $state('');
	let activePattern = $state('all');

	const patterns = $derived(() => {
		const counts: Record<string, number> = {};
		for (const s of data.scenarios) {
			counts[s.pattern] = (counts[s.pattern] ?? 0) + 1;
		}
		return Object.entries(counts).sort((a, b) => b[1] - a[1]);
	});

	const filtered = $derived(() => {
		let list = data.scenarios;
		if (activePattern !== 'all') {
			list = list.filter((s) => s.pattern === activePattern);
		}
		if (search.trim()) {
			const q = search.trim().toLowerCase();
			list = list.filter(
				(s) =>
					s.name.toLowerCase().includes(q) ||
					s.description.toLowerCase().includes(q) ||
					s.entities.some((e) => e.toLowerCase().includes(q)) ||
					String(s.id).includes(q)
			);
		}
		return list;
	});
</script>

<div class="page">
	<div class="header">
		<h1>Crash Scenarios</h1>
		<p class="subtitle">{data.scenarios.length} generated scenarios &middot; {filtered().length} shown</p>
	</div>

	<div class="controls">
		<div class="filters">
			<button
				class="filter-btn"
				class:active={activePattern === 'all'}
				onclick={() => (activePattern = 'all')}
			>
				All <span class="count">{data.scenarios.length}</span>
			</button>
			{#each patterns() as [pattern, count]}
				<button
					class="filter-btn"
					class:active={activePattern === pattern}
					style="--pattern-color: {patternColors[pattern] ?? '#60a5fa'}"
					onclick={() => (activePattern = activePattern === pattern ? 'all' : pattern)}
				>
					{patternLabels[pattern] ?? pattern} <span class="count">{count}</span>
				</button>
			{/each}
		</div>
		<input
			type="text"
			class="search"
			placeholder="Search scenarios..."
			bind:value={search}
		/>
	</div>

	{#if filtered().length === 0}
		<div class="empty">No scenarios match your filter.</div>
	{:else}
		<div class="grid">
			{#each filtered() as scenario (scenario.id)}
				<ScenarioCard {scenario} />
			{/each}
		</div>
	{/if}
</div>

<style>
	.page {
		display: flex;
		flex-direction: column;
		gap: 20px;
	}

	.header {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	h1 {
		font-size: 1.75rem;
		font-weight: 700;
		letter-spacing: -0.02em;
	}

	.subtitle {
		color: var(--color-muted);
		font-size: 0.9rem;
	}

	.controls {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}

	.filter-btn {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 6px 14px;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 20px;
		color: var(--color-muted);
		font-size: 0.8rem;
		font-weight: 500;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.filter-btn:hover {
		border-color: var(--color-accent);
		color: var(--color-text);
	}

	.filter-btn.active {
		background: var(--pattern-color, var(--color-accent));
		border-color: var(--pattern-color, var(--color-accent));
		color: #0f1117;
		font-weight: 600;
	}

	.count {
		font-size: 0.7rem;
		opacity: 0.7;
	}

	.search {
		padding: 10px 16px;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 8px;
		color: var(--color-text);
		font-size: 0.85rem;
		outline: none;
		transition: border-color 0.15s ease;
		max-width: 400px;
	}

	.search:focus {
		border-color: var(--color-accent);
	}

	.search::placeholder {
		color: var(--color-muted);
	}

	.empty {
		text-align: center;
		padding: 48px;
		color: var(--color-muted);
		font-size: 0.9rem;
	}

	.grid {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 20px;
	}

	@media (max-width: 900px) {
		.grid {
			grid-template-columns: repeat(2, 1fr);
		}
	}

	@media (max-width: 560px) {
		.grid {
			grid-template-columns: 1fr;
		}

		.filters {
			gap: 6px;
		}

		.filter-btn {
			padding: 4px 10px;
			font-size: 0.75rem;
		}
	}
</style>
