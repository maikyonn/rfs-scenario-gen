<script lang="ts">
	import type { ExperimentResult } from '$lib/types';
	import RatingWidget from './RatingWidget.svelte';

	let { result, methods }: {
		result: ExperimentResult;
		methods: string[];
	} = $props();

	function fmtDuration(ms: number): string {
		const s = ms / 1000;
		return `${s.toFixed(1)}s`;
	}

	function formatConfig(json: string | null): string {
		if (!json) return 'No config available';
		try {
			return JSON.stringify(JSON.parse(json), null, 2);
		} catch {
			return json;
		}
	}
</script>

<div class="sbs-container">
	<!-- Record header -->
	<div class="record-header">
		{#if result.record.tldr}
			<p class="record-tldr">{result.record.tldr}</p>
		{/if}
		<div class="record-meta">
			<span class="crash-badge">{result.record.crash_type}</span>
			{#if result.record.pattern}
				<span class="pattern-badge">{result.record.pattern}</span>
			{/if}
			{#if result.record.road_context && result.record.road_context !== 'unspecified'}
				<span class="road-badge">{result.record.road_context}</span>
			{/if}
		</div>
		<details class="desc-details">
			<summary class="desc-toggle">Full description</summary>
			<p class="record-desc">{result.record.text_desc}</p>
		</details>
	</div>

	<!-- Columns -->
	<div class="columns">
		{#each methods as method}
			{@const gen = result.generations[method]}
			<div class="column">
				<h4 class="col-header">{method}</h4>

				{#if gen == null}
					<div class="empty-state">Not generated</div>
				{:else}
					<!-- Video -->
					<div class="video-area">
						{#if gen.mp4_url}
							<video controls preload="metadata" class="video-player">
								<source src={gen.mp4_url} type="video/mp4" />
								<p>Video not supported</p>
							</video>
						{:else}
							<div class="video-placeholder">
								<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
									<rect x="2" y="4" width="20" height="16" rx="2" />
									<path d="M10 9l5 3-5 3V9z" />
								</svg>
								<span>No video</span>
							</div>
						{/if}
					</div>

					<!-- Collision status -->
					<div class="info-row">
						{#if gen.status === 'failed'}
							<span class="status-fail">
								<svg viewBox="0 0 16 16" fill="none" class="status-icon">
									<path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
								</svg>
								Failed
							</span>
						{:else if gen.collision_detected}
							<span class="status-collision">
								<svg viewBox="0 0 16 16" fill="none" class="status-icon">
									<path d="M3 8l3.5 3.5L13 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
								</svg>
								Collision at {gen.collision_time?.toFixed(2)}s
							</span>
						{:else}
							<span class="status-no-collision">
								<svg viewBox="0 0 16 16" fill="none" class="status-icon">
									<path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
								</svg>
								No collision
							</span>
						{/if}
					</div>

					<!-- Duration -->
					{#if gen.duration_ms != null}
						<div class="info-row info-secondary">
							Generation time: {fmtDuration(gen.duration_ms)}
						</div>
					{/if}

					<!-- Rating -->
					<div class="info-row">
						<RatingWidget generationId={gen.id} currentRating={gen.avg_rating} />
					</div>

					<!-- Error -->
					{#if gen.error}
						<div class="error-msg">{gen.error}</div>
					{/if}

					<!-- Config -->
					{#if gen.config_json}
						<details class="config-details">
							<summary class="config-toggle">Config JSON</summary>
							<pre class="config-pre">{formatConfig(gen.config_json)}</pre>
						</details>
					{/if}
				{/if}
			</div>
		{/each}
	</div>
</div>

<style>
	.sbs-container {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 8px;
		padding: 16px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}

	.record-header {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.record-tldr {
		margin: 0;
		font-size: 0.9rem;
		color: var(--color-text);
		line-height: 1.5;
		font-weight: 500;
	}

	.desc-details {
		margin-top: 2px;
	}

	.desc-toggle {
		font-size: 0.75rem;
		color: var(--color-muted);
		cursor: pointer;
		user-select: none;
		list-style: none;
	}

	.desc-toggle::-webkit-details-marker {
		display: none;
	}

	.desc-toggle:hover {
		color: var(--color-accent);
	}

	.record-desc {
		margin: 6px 0 0 0;
		font-size: 0.8rem;
		color: var(--color-muted);
		line-height: 1.5;
	}

	.record-meta {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
	}

	.crash-badge {
		font-size: 0.7rem;
		font-weight: 600;
		padding: 2px 8px;
		border-radius: 4px;
		background: rgba(248, 113, 113, 0.12);
		color: #f87171;
	}

	.pattern-badge {
		font-size: 0.7rem;
		font-weight: 600;
		padding: 2px 8px;
		border-radius: 4px;
		background: var(--color-accent-dim);
		color: var(--color-accent);
	}

	.road-badge {
		font-size: 0.7rem;
		font-weight: 500;
		padding: 2px 8px;
		border-radius: 4px;
		background: rgba(96, 165, 250, 0.12);
		color: #60a5fa;
	}

	.columns {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
		gap: 16px;
	}

	.column {
		display: flex;
		flex-direction: column;
		gap: 10px;
		background: var(--color-bg);
		border: 1px solid var(--color-border);
		border-radius: 6px;
		padding: 12px;
	}

	.col-header {
		margin: 0;
		font-size: 0.82rem;
		font-weight: 600;
		color: var(--color-accent);
		font-family: 'SF Mono', 'Fira Code', monospace;
		text-transform: lowercase;
	}

	.empty-state {
		font-size: 0.82rem;
		color: var(--color-muted);
		font-style: italic;
		padding: 16px 0;
		text-align: center;
	}

	.video-area {
		border-radius: 6px;
		overflow: hidden;
		background: #000;
	}

	.video-player {
		width: 100%;
		display: block;
	}

	.video-placeholder {
		aspect-ratio: 16 / 9;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 8px;
		color: var(--color-muted);
	}

	.video-placeholder svg {
		width: 40px;
		height: 40px;
	}

	.video-placeholder span {
		font-size: 0.78rem;
	}

	.info-row {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 0.82rem;
	}

	.info-secondary {
		color: var(--color-muted);
	}

	.status-icon {
		width: 14px;
		height: 14px;
		flex-shrink: 0;
	}

	.status-collision {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		color: #4ade80;
		font-weight: 500;
	}

	.status-no-collision {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		color: var(--color-muted);
	}

	.status-fail {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		color: #f87171;
		font-weight: 500;
	}

	.error-msg {
		font-size: 0.78rem;
		color: #f87171;
		padding: 8px 10px;
		background: rgba(248, 113, 113, 0.06);
		border: 1px solid rgba(248, 113, 113, 0.15);
		border-radius: 4px;
		line-height: 1.4;
	}

	.config-details {
		margin-top: 2px;
	}

	.config-toggle {
		font-size: 0.75rem;
		color: var(--color-muted);
		cursor: pointer;
		user-select: none;
		list-style: none;
	}

	.config-toggle::-webkit-details-marker {
		display: none;
	}

	.config-toggle:hover {
		color: var(--color-accent);
	}

	.config-pre {
		margin: 6px 0 0 0;
		padding: 8px;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 4px;
		font-size: 0.7rem;
		line-height: 1.45;
		color: var(--color-muted);
		overflow-x: auto;
		white-space: pre;
		max-height: 240px;
		overflow-y: auto;
		font-family: 'SF Mono', 'Fira Code', monospace;
	}

	.config-pre::-webkit-scrollbar {
		width: 4px;
		height: 4px;
	}
	.config-pre::-webkit-scrollbar-thumb {
		background: var(--color-border);
		border-radius: 4px;
	}
</style>
