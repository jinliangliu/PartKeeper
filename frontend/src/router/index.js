import { createRouter, createWebHistory } from 'vue-router'
import { authStore } from '../stores/auth'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/Login.vue'),
    meta: { public: true, title: '登录' }
  },
  {
    path: '/',
    component: () => import('../layout/MainLayout.vue'),
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', name: 'dashboard', component: () => import('../views/Dashboard.vue'), meta: { title: '仪表盘' } },
      { path: 'components', name: 'components', component: () => import('../views/Components.vue'), meta: { title: '物品管理' } },
      { path: 'categories', name: 'categories', component: () => import('../views/Categories.vue'), meta: { title: '分类管理' } },
      { path: 'suppliers', name: 'suppliers', component: () => import('../views/Suppliers.vue'), meta: { title: '供应商管理' } },
      { path: 'locations', name: 'locations', component: () => import('../views/Locations.vue'), meta: { title: '库位管理' } },
      { path: 'boms', name: 'boms', component: () => import('../views/Boms.vue'), meta: { title: 'BOM 管理' } },
      { path: 'stock-in', name: 'stock-in', component: () => import('../views/StockMovement.vue'), meta: { title: '入库操作', mode: 'in' } },
      { path: 'stock-out', name: 'stock-out', component: () => import('../views/StockMovement.vue'), meta: { title: '出库操作', mode: 'out' } },
      { path: 'transactions', name: 'transactions', component: () => import('../views/Transactions.vue'), meta: { title: '库存流水' } },
      { path: 'low-stock', name: 'low-stock', component: () => import('../views/LowStock.vue'), meta: { title: '低库存预警' } },
      { path: 'statistics', name: 'statistics', component: () => import('../views/Statistics.vue'), meta: { title: '统计分析' } },
      { path: 'utility-bills', name: 'utility-bills', component: () => import('../views/UtilityBills.vue'), meta: { title: '生活缴费' } },
      { path: 'expenses', name: 'expenses', component: () => import('../views/Expenses.vue'), meta: { title: '家庭开支' } },
      { path: 'users', name: 'users', component: () => import('../views/Users.vue'), meta: { title: '用户管理', admin: true } }
    ]
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to) => {
  document.title = (to.meta.title ? `${to.meta.title} - ` : '') + '物料管理系统'

  if (to.meta.public) {
    if (authStore.isLoggedIn && to.path === '/login') {
      return '/dashboard'
    }
    return true
  }

  if (!authStore.isLoggedIn) {
    return '/login'
  }
  if (to.meta.admin && !authStore.isAdmin) {
    return '/dashboard'
  }
  return true
})

export default router
