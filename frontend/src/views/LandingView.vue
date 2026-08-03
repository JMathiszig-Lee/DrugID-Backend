<template>
  <div class="page landing-page">
    <section class="hero">
      <div class="hero-copy">
        <span class="eyebrow">Visual recognition research</span>
        <h1>How quickly can clinicians identify a drug ampoule?</h1>
        <p class="lede">
          This study compares reaction times across three ampoule presentation styles. Every
          participant completes all three groups in an individually randomised order.
        </p>
        <div class="button-row">
          <RouterLink class="button button--primary" :to="{ name: 'register' }">
            Register to take part
          </RouterLink>
          <RouterLink class="button button--quiet" :to="{ name: 'returning-participant' }">
            Return to my study
          </RouterLink>
          <a class="text-link" href="#how-it-works">How it works</a>
        </div>
      </div>

      <aside class="hero-panel" aria-label="Study at a glance">
        <div class="ampoule-silhouette" aria-hidden="true">
          <span></span>
        </div>
        <dl>
          <div>
            <dt>3</dt>
            <dd>presentation groups</dd>
          </div>
          <div>
            <dt>1</dt>
            <dd>secure email link</dd>
          </div>
          <div>
            <dt>All</dt>
            <dd>trials saved automatically</dd>
          </div>
        </dl>
      </aside>
    </section>

    <section id="how-it-works" class="section-block" aria-labelledby="process-heading">
      <span class="eyebrow">Simple, consistent, measurable</span>
      <h2 id="process-heading">What you will do</h2>
      <ol class="step-grid">
        <li>
          <span>01</span>
          <h3>Register</h3>
          <p>New participants tell us their speciality and years of clinical experience once.</p>
        </li>
        <li>
          <span>02</span>
          <h3>Open your link</h3>
          <p>Use the one-time link sent to your email to enter your study session.</p>
        </li>
        <li>
          <span>03</span>
          <h3>Select ampoules</h3>
          <p>Choose the requested drug before the on-screen timer reaches zero.</p>
        </li>
      </ol>
    </section>

    <section class="section-block split-section" aria-labelledby="before-heading">
      <div>
        <span class="eyebrow">Before you begin</span>
        <h2 id="before-heading">Use a stable connection and a comfortable screen</h2>
      </div>
      <ul class="check-list">
        <li>Complete the study somewhere you can concentrate without interruption.</li>
        <li>Wait for every ampoule image to load; timing starts only when they appear.</li>
        <li>Your group order and study settings are assigned by the research server.</li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.landing-page {
  gap: clamp(4rem, 9vw, 7rem);
}

.hero {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(18rem, 0.65fr);
  gap: clamp(2rem, 7vw, 6rem);
  align-items: center;
  min-height: min(41rem, calc(100vh - 8rem));
  padding: clamp(3rem, 7vw, 6rem) 0;
}

.hero-copy {
  display: grid;
  gap: 1.5rem;
}

.hero h1 {
  max-width: 13ch;
  margin: 0;
  font-size: clamp(2.75rem, 7vw, 5.7rem);
  line-height: 0.98;
  letter-spacing: -0.055em;
}

.hero .lede {
  max-width: 42rem;
}

.hero-panel {
  position: relative;
  display: grid;
  gap: 2rem;
  overflow: hidden;
  padding: clamp(1.5rem, 4vw, 2.5rem);
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: var(--radius-lg);
  background: var(--navy);
  color: white;
  box-shadow: var(--shadow-lg);
}

.hero-panel::before {
  position: absolute;
  inset: -30% -50% auto auto;
  width: 17rem;
  height: 17rem;
  border-radius: 50%;
  background: rgba(34, 193, 190, 0.18);
  content: '';
}

.ampoule-silhouette {
  display: grid;
  place-items: center;
  min-height: 15rem;
}

.ampoule-silhouette span {
  position: relative;
  display: block;
  width: 4.75rem;
  height: 14rem;
  border: 3px solid rgba(255, 255, 255, 0.78);
  border-radius: 2rem 2rem 1rem 1rem;
  transform: rotate(8deg);
}

.ampoule-silhouette span::before {
  position: absolute;
  top: -2.1rem;
  left: 50%;
  width: 2rem;
  height: 2.2rem;
  border: 3px solid rgba(255, 255, 255, 0.78);
  border-bottom: 0;
  border-radius: 0.7rem 0.7rem 0 0;
  content: '';
  transform: translateX(-50%);
}

.ampoule-silhouette span::after {
  position: absolute;
  inset: 4rem -0.45rem auto;
  height: 5.2rem;
  border-radius: 0.45rem;
  background: var(--amber);
  content: '';
}

.hero-panel dl {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
  margin: 0;
}

.hero-panel dl div {
  display: grid;
  gap: 0.2rem;
}

.hero-panel dt {
  font-size: 1.5rem;
  font-weight: 800;
}

.hero-panel dd {
  margin: 0;
  color: rgba(255, 255, 255, 0.68);
  font-size: 0.78rem;
  line-height: 1.35;
}

.section-block {
  scroll-margin-top: 7rem;
}

.section-block h2 {
  max-width: 18ch;
  margin: 0.5rem 0 2rem;
  font-size: clamp(2rem, 5vw, 3.6rem);
  line-height: 1.05;
  letter-spacing: -0.035em;
}

.step-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
  padding: 0;
  list-style: none;
}

.step-grid li {
  min-height: 12rem;
  padding: 1.5rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.step-grid li > span {
  color: var(--blue);
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.09em;
}

.step-grid h3 {
  margin: 2.3rem 0 0.5rem;
  font-size: 1.3rem;
}

.step-grid p {
  margin: 0;
  color: var(--ink-muted);
}

.split-section {
  display: grid;
  grid-template-columns: minmax(0, 0.85fr) minmax(20rem, 1.15fr);
  gap: clamp(2rem, 8vw, 7rem);
  align-items: start;
  padding: clamp(2rem, 5vw, 4rem);
  border-radius: var(--radius-lg);
  background: var(--navy);
  color: white;
}

.split-section h2 {
  margin-bottom: 0;
}

.split-section .eyebrow {
  color: var(--teal-light);
}

.check-list {
  display: grid;
  gap: 1.25rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.check-list li {
  position: relative;
  padding: 0 0 1.25rem 2.25rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.16);
  color: rgba(255, 255, 255, 0.82);
}

.check-list li::before {
  position: absolute;
  top: 0.05rem;
  left: 0;
  display: grid;
  place-items: center;
  width: 1.35rem;
  height: 1.35rem;
  border-radius: 50%;
  background: var(--teal);
  color: var(--navy);
  content: '✓';
  font-size: 0.78rem;
  font-weight: 900;
}

@media (max-width: 850px) {
  .hero,
  .split-section {
    grid-template-columns: 1fr;
  }

  .hero {
    min-height: 0;
  }

  .hero-copy {
    justify-items: start;
  }

  .hero-panel {
    grid-template-columns: 0.55fr 1.45fr;
    align-items: center;
  }

  .ampoule-silhouette {
    min-height: 12rem;
  }

  .hero-panel dl {
    grid-template-columns: 1fr;
  }

  .step-grid {
    grid-template-columns: 1fr;
  }

  .step-grid li {
    min-height: 0;
  }

  .step-grid h3 {
    margin-top: 1rem;
  }
}

@media (max-width: 520px) {
  .hero-panel {
    grid-template-columns: 1fr;
  }

  .hero-panel dl {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
