<template>
  <div class="page centre-page">
    <section class="message-card">
      <span class="eyebrow">404</span>
      <h1>That page is not part of the study</h1>
      <p class="lede">Return to the study information or use the secure link in your email.</p>
      <RouterLink class="button button--primary" :to="{ name: 'landing' }">Return home</RouterLink>
    </section>
  </div>
</template>
