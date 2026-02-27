<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	onMount(() => {
		goto('/experiments', { replaceState: true });
	});
</script>

<div class="loading">Redirecting...</div>

<style>
	.loading {
		text-align: center;
		padding: 48px;
		color: var(--color-muted);
	}
</style>
