<template>
  <a class="skip-link" href="#main-content">Skip to main content</a>

  <div class="app-shell">
    <header class="site-header">
      <RouterLink class="brand" :to="{ name: 'landing' }" aria-label="Ampoule study home">
        <span class="brand-mark" aria-hidden="true"></span>
        <span>
          <strong>Ampoule</strong>
          <small>recognition study</small>
        </span>
      </RouterLink>

      <nav aria-label="Primary navigation">
        <RouterLink :to="{ name: 'landing' }">About</RouterLink>
        <RouterLink class="nav-join" :to="{ name: 'register' }">Take part</RouterLink>
      </nav>
    </header>

    <main id="main-content" tabindex="-1">
      <RouterView />
    </main>

    <footer class="site-footer">
      <p>Drug ampoule recognition research</p>
      <p>Responses are recorded only after you sign in through your study link.</p>
    </footer>
  </div>
</template>
