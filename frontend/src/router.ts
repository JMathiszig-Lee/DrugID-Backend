import { createRouter, createWebHistory } from 'vue-router'
import LandingView from './views/LandingView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'landing',
      component: LandingView,
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('./views/RegisterView.vue'),
    },
    {
      path: '/check-email',
      name: 'check-email',
      component: () => import('./views/CheckEmailView.vue'),
    },
    {
      path: '/verify',
      name: 'verify',
      component: () => import('./views/VerifyView.vue'),
    },
    {
      path: '/study',
      name: 'study',
      component: () => import('./views/StudyView.vue'),
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('./views/NotFoundView.vue'),
    },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
