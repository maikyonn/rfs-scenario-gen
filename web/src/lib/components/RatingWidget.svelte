<script lang="ts">
	import { submitRating } from '$lib/api';

	let { generationId, currentRating }: {
		generationId: string;
		currentRating: number | null;
	} = $props();

	let localRating = $state<number | null>(null);
	let rating = $derived(localRating ?? currentRating ?? 0);
	let hoverRating = $state(0);
	let submitting = $state(false);

	async function handleClick(star: number) {
		if (submitting) return;
		localRating = star;
		submitting = true;
		try {
			await submitRating({ generation_id: generationId, rating: star });
		} catch {
			// silently fail, rating is shown optimistically
		} finally {
			submitting = false;
		}
	}

	function displayRating(index: number): boolean {
		if (hoverRating > 0) return index <= hoverRating;
		return index <= rating;
	}
</script>

<div class="rating-widget" class:submitting>
	{#each [1, 2, 3, 4, 5] as star}
		<button
			class="star-btn"
			class:filled={displayRating(star)}
			onclick={() => handleClick(star)}
			onmouseenter={() => { hoverRating = star; }}
			onmouseleave={() => { hoverRating = 0; }}
			disabled={submitting}
			aria-label="Rate {star} of 5"
		>
			{#if displayRating(star)}
				&#9733;
			{:else}
				&#9734;
			{/if}
		</button>
	{/each}
</div>

<style>
	.rating-widget {
		display: inline-flex;
		gap: 2px;
		align-items: center;
	}

	.rating-widget.submitting {
		opacity: 0.6;
	}

	.star-btn {
		background: none;
		border: none;
		cursor: pointer;
		font-size: 1.1rem;
		padding: 0 1px;
		line-height: 1;
		color: var(--color-muted);
		transition: color 0.1s, transform 0.1s;
	}

	.star-btn:disabled {
		cursor: wait;
	}

	.star-btn.filled {
		color: #facc15;
	}

	.star-btn:hover:not(:disabled) {
		transform: scale(1.2);
	}
</style>
