<script lang="ts">
	import type { Scenario } from '$lib/data/scenarios';
	import { patternLabels, patternColors } from '$lib/data/scenarios';

	let { scenario }: { scenario: Scenario } = $props();
</script>

<div class="metadata">
	<div class="row">
		<span class="label">Pattern</span>
		<span class="value">
			<span
				class="pattern-pill"
				style="background: {patternColors[scenario.pattern] ?? '#60a5fa'}20; color: {patternColors[scenario.pattern] ?? '#60a5fa'}"
			>
				{patternLabels[scenario.pattern] ?? scenario.pattern}
			</span>
		</span>
	</div>
	<div class="row">
		<span class="label">Roads</span>
		<span class="value">{scenario.roads}</span>
	</div>
	<div class="row">
		<span class="label">Junction</span>
		<span class="value">{scenario.junction}</span>
	</div>
	<div class="row">
		<span class="label">Speeds</span>
		<span class="value">{scenario.speeds}</span>
	</div>
	<div class="row">
		<span class="label">Entities</span>
		<span class="value entities">
			{#each scenario.entities as entity}
				<span class="pill">{entity}</span>
			{/each}
		</span>
	</div>
	<div class="row">
		<span class="label">Duration</span>
		<span class="value">{scenario.duration}</span>
	</div>
</div>

<style>
	.metadata {
		display: flex;
		flex-direction: column;
		gap: 0;
		border: 1px solid var(--color-border);
		border-radius: 8px;
		overflow: hidden;
	}

	.row {
		display: flex;
		align-items: center;
		padding: 12px 16px;
		border-bottom: 1px solid var(--color-border);
	}

	.row:last-child {
		border-bottom: none;
	}

	.label {
		width: 100px;
		flex-shrink: 0;
		font-size: 0.8rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--color-muted);
	}

	.value {
		font-size: 0.9rem;
		color: var(--color-text);
	}

	.entities {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}

	.pill {
		display: inline-block;
		font-size: 0.8rem;
		padding: 2px 10px;
		background: var(--color-accent-dim);
		color: var(--color-accent);
		border-radius: 12px;
	}

	.pattern-pill {
		display: inline-block;
		font-size: 0.8rem;
		font-weight: 600;
		padding: 2px 10px;
		border-radius: 12px;
	}
</style>
