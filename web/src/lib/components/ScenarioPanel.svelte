<script lang="ts">
	let { videoUrl, thumbnailUrl, config, validated, xoscUrl }: {
		videoUrl: string | null;
		thumbnailUrl: string | null;
		config: Record<string, unknown> | null;
		validated: boolean;
		xoscUrl: string | null;
	} = $props();

	function patternLabel(p: string): string {
		const map: Record<string, string> = {
			junction_tbone:       'T-bone (Junction)',
			rear_end:             'Rear-end',
			head_on:              'Head-on',
			sideswipe:            'Sideswipe',
			pedestrian_crossing:  'Pedestrian crossing',
			dooring:              'Dooring',
			parking_backing:      'Parking / backing',
		};
		return map[p] ?? p;
	}

	function entitySummary(entity: Record<string, unknown>): string {
		const type = (entity.entity_type as string) ?? 'vehicle';
		const speed = entity.speed_kmh ?? entity.speed_mps;
		const speedStr = speed != null ? ` @ ${speed}${entity.speed_kmh != null ? ' km/h' : ' m/s'}` : '';
		return `${type}${speedStr}`;
	}

	const entities = $derived(
		config && Array.isArray(config.entities)
			? (config.entities as Record<string, unknown>[])
			: []
	);
</script>

<div class="panel">
	{#if videoUrl}
		<!-- svelte-ignore a11y_media_has_caption -->
		<video
			src={videoUrl}
			poster={thumbnailUrl ?? undefined}
			controls
			autoplay
			loop
			class="video"
		></video>
	{:else}
		<div class="placeholder">
			<svg viewBox="0 0 48 48" fill="none" class="placeholder-icon">
				<rect x="6" y="12" width="36" height="26" rx="3" stroke="currentColor" stroke-width="2"/>
				<path d="M20 19l10 5-10 5V19z" fill="currentColor" opacity="0.4"/>
			</svg>
			<p>Video will appear here after rendering</p>
		</div>
	{/if}

	{#if validated || config}
		<div class="meta">
			{#if validated}
				<div class="badge badge-ok">
					<svg viewBox="0 0 12 12" fill="none" class="badge-icon">
						<path d="M2 6l2.5 2.5L10 3.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
					</svg>
					Collision validated
				</div>
			{/if}

			{#if config}
				{#if config.crash_pattern}
					<div class="meta-row">
						<span class="meta-label">Pattern</span>
						<span class="meta-value">{patternLabel(config.crash_pattern as string)}</span>
					</div>
				{/if}

				{#if config.scenario_name}
					<div class="meta-row">
						<span class="meta-label">Scenario</span>
						<span class="meta-value mono">{config.scenario_name}</span>
					</div>
				{/if}

				{#if entities.length > 0}
					<div class="meta-row">
						<span class="meta-label">Entities</span>
						<span class="meta-value">
							{#each entities as entity, i}
								<span class="entity-chip">{entitySummary(entity)}</span>
							{/each}
						</span>
					</div>
				{/if}
			{/if}
		</div>
	{/if}

	{#if videoUrl || xoscUrl}
		<div class="downloads">
			{#if videoUrl}
				<a href={videoUrl} download class="btn-dl">↓ MP4</a>
			{/if}
			{#if xoscUrl}
				<a href={xoscUrl} download class="btn-dl">↓ .xosc</a>
			{/if}
		</div>
	{/if}
</div>

<style>
	.panel {
		display: flex;
		flex-direction: column;
		gap: 12px;
		height: 100%;
	}

	.video {
		width: 100%;
		border-radius: 8px;
		background: #000;
		display: block;
		aspect-ratio: 16/9;
		object-fit: cover;
	}

	.placeholder {
		aspect-ratio: 16/9;
		border-radius: 8px;
		border: 1px dashed var(--color-border);
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 10px;
		color: var(--color-muted);
	}

	.placeholder-icon {
		width: 40px;
		height: 40px;
		color: var(--color-border);
	}

	.placeholder p {
		font-size: 0.8rem;
		text-align: center;
	}

	.meta {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.badge {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		font-size: 0.75rem;
		font-weight: 600;
		padding: 3px 9px;
		border-radius: 20px;
		width: fit-content;
	}

	.badge-ok {
		color: #4ade80;
		background: rgba(74, 222, 128, 0.1);
		border: 1px solid rgba(74, 222, 128, 0.25);
	}

	.badge-icon {
		width: 12px;
		height: 12px;
	}

	.meta-row {
		display: flex;
		gap: 8px;
		align-items: flex-start;
		font-size: 0.82rem;
	}

	.meta-label {
		color: var(--color-muted);
		font-size: 0.75rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		width: 68px;
		flex-shrink: 0;
		padding-top: 1px;
	}

	.meta-value {
		color: var(--color-text);
		display: flex;
		flex-wrap: wrap;
		gap: 4px;
		flex: 1;
	}

	.mono {
		font-family: ui-monospace, monospace;
		font-size: 0.78rem;
	}

	.entity-chip {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 4px;
		padding: 1px 7px;
		font-size: 0.75rem;
		color: var(--color-muted);
	}

	.downloads {
		display: flex;
		gap: 8px;
	}

	.btn-dl {
		padding: 5px 12px;
		border: 1px solid var(--color-border);
		border-radius: 6px;
		font-size: 0.78rem;
		color: var(--color-muted);
		text-decoration: none;
		transition: color 0.15s, border-color 0.15s;
	}

	.btn-dl:hover {
		color: var(--color-accent);
		border-color: rgba(96, 165, 250, 0.4);
	}
</style>
