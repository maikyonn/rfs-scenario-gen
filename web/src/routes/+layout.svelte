<script lang="ts">
	let { children } = $props();
</script>

<svelte:head>
	<title>RFS Crash Scenario Viewer</title>
	<meta name="description" content="View and analyze crash scenarios generated for road safety simulation" />
</svelte:head>

<div class="app">
	<header>
		<a href="/" class="logo">RFS Crash Scenario Viewer</a>
		<nav>
			<a href="/" class="nav-link">Scenarios</a>
			<a href="/generate" class="nav-link nav-link--accent">Generate</a>
		</nav>
	</header>
	<main>
		{@render children()}
	</main>
</div>

<style>
	:global(*) {
		box-sizing: border-box;
		margin: 0;
		padding: 0;
	}

	:global(html) {
		--color-bg: #0f1117;
		--color-surface: #1a1d27;
		--color-border: #2a2d3a;
		--color-text: #e4e4e7;
		--color-muted: #8b8d98;
		--color-accent: #60a5fa;
		--color-accent-dim: rgba(96, 165, 250, 0.12);
		--color-accent-hover: #93c5fd;

		font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial,
			sans-serif;
		background: var(--color-bg);
		color: var(--color-text);
		line-height: 1.6;
	}

	:global(body) {
		min-height: 100vh;
	}

	.app {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
	}

	header {
		padding: 16px 24px;
		border-bottom: 1px solid var(--color-border);
		background: var(--color-surface);
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	.logo {
		font-size: 1.1rem;
		font-weight: 700;
		color: var(--color-text);
		text-decoration: none;
		letter-spacing: -0.01em;
	}

	.logo:hover {
		color: var(--color-accent);
	}

	nav {
		display: flex;
		gap: 8px;
	}

	.nav-link {
		padding: 6px 14px;
		border-radius: 6px;
		font-size: 0.875rem;
		font-weight: 500;
		text-decoration: none;
		color: var(--color-muted);
		transition: color 0.15s, background 0.15s;
	}

	.nav-link:hover {
		color: var(--color-text);
		background: rgba(255, 255, 255, 0.06);
	}

	.nav-link--accent {
		color: var(--color-accent);
		border: 1px solid rgba(96, 165, 250, 0.3);
	}

	.nav-link--accent:hover {
		background: var(--color-accent-dim);
		color: var(--color-accent-hover);
	}

	main {
		flex: 1;
		padding: 32px 24px;
		max-width: 1200px;
		width: 100%;
		margin: 0 auto;
	}
</style>
