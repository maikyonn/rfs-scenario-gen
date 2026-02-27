<script lang="ts">
	import type { Scenario } from '$lib/data/scenarios';
	import { patternLabels, patternColors } from '$lib/data/scenarios';

	let { scenario }: { scenario: Scenario } = $props();

	let imgFailed = $state(false);

	function truncate(text: string, max: number): string {
		if (text.length <= max) return text;
		return text.slice(0, max) + '...';
	}
</script>

<a href="/scenario/{scenario.id}" class="card">
	<div class="thumbnail">
		{#if imgFailed}
			<div class="placeholder">
				<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
					<rect x="2" y="2" width="20" height="20" rx="2" />
					<circle cx="8.5" cy="8.5" r="1.5" />
					<path d="m21 15-5-5L5 21" />
				</svg>
				<span>No thumbnail</span>
			</div>
		{:else}
			<img
				src={scenario.thumbnailPath}
				alt="Thumbnail for {scenario.name}"
				onerror={() => { imgFailed = true; }}
			/>
		{/if}
		<span class="id-badge">#{scenario.id}</span>
	</div>
	<div class="body">
		<div class="title-row">
			<h3>{scenario.name}</h3>
		</div>
		<p>{truncate(scenario.description, 100)}</p>
		<div class="meta">
			<span
				class="pattern-tag"
				style="background: {patternColors[scenario.pattern] ?? '#60a5fa'}20; color: {patternColors[scenario.pattern] ?? '#60a5fa'}"
			>
				{patternLabels[scenario.pattern] ?? scenario.pattern}
			</span>
			<span class="road-tag">{scenario.roads}</span>
		</div>
	</div>
</a>

<style>
	.card {
		display: flex;
		flex-direction: column;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 8px;
		overflow: hidden;
		text-decoration: none;
		color: inherit;
		transition: transform 0.15s ease, box-shadow 0.15s ease;
	}

	.card:hover {
		transform: translateY(-2px);
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
	}

	.thumbnail {
		aspect-ratio: 16 / 9;
		background: var(--color-bg);
		overflow: hidden;
		position: relative;
	}

	.thumbnail img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}

	.id-badge {
		position: absolute;
		top: 8px;
		right: 8px;
		font-size: 0.7rem;
		font-weight: 700;
		padding: 2px 8px;
		background: rgba(0, 0, 0, 0.7);
		color: var(--color-text);
		border-radius: 4px;
	}

	.placeholder {
		width: 100%;
		height: 100%;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 8px;
		color: var(--color-muted);
	}

	.placeholder svg {
		width: 48px;
		height: 48px;
	}

	.placeholder span {
		font-size: 0.8rem;
	}

	.body {
		padding: 14px 16px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.title-row {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	h3 {
		margin: 0;
		font-size: 0.95rem;
		font-weight: 600;
		color: var(--color-text);
		line-height: 1.3;
	}

	p {
		margin: 0;
		font-size: 0.82rem;
		color: var(--color-muted);
		line-height: 1.4;
	}

	.meta {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-top: 4px;
		flex-wrap: wrap;
	}

	.pattern-tag {
		font-size: 0.7rem;
		font-weight: 600;
		padding: 2px 8px;
		border-radius: 4px;
	}

	.road-tag {
		font-size: 0.7rem;
		padding: 2px 8px;
		background: var(--color-accent-dim);
		color: var(--color-accent);
		border-radius: 4px;
	}
</style>
