<template>
  <div>
    <el-row :gutter="16" class="stat-row">
      <el-col :span="6" v-for="card in cards" :key="card.label">
        <el-card shadow="hover">
          <div class="stat">
            <div class="value" :class="{ danger: card.danger }">{{ card.value }}</div>
            <div class="label">{{ card.label }}</div>
            <div class="sub">{{ card.sub }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="mt">
      <template #header>
        <div class="card-head">
          <span>家庭消费趋势（近 6 月）</span>
          <span class="legend">
            <i class="dot utility" />缴费
            <i class="dot expense" />开支
          </span>
        </div>
      </template>
      <div ref="trendRef" class="chart"></div>
    </el-card>

    <el-row :gutter="16" class="mt">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div class="card-head">
              <span>最近开支</span>
              <el-button link type="primary" @click="go('/expenses')">查看全部</el-button>
            </div>
          </template>
          <el-table :data="recentExpenses" border stripe empty-text="暂无开支记录">
            <el-table-column prop="occurred_at" label="日期" width="100" />
            <el-table-column label="类型" width="80">
              <template #default="{ row }">
                <el-tag size="small">{{ row.category_label }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="merchant" label="商户" min-width="110" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="muted">{{ row.merchant || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="金额" width="100" align="right">
              <template #default="{ row }">
                <span class="money">¥{{ row.amount }}</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div class="card-head">
              <span>最近出入库</span>
              <el-button link type="primary" @click="go('/transactions')">查看全部</el-button>
            </div>
          </template>
          <el-table :data="recent" border stripe empty-text="暂无流水">
            <el-table-column prop="component_name" label="物料" min-width="120" show-overflow-tooltip />
            <el-table-column label="类型" width="80" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="row.type === 'in' ? 'success' : 'danger'">
                  {{ row.type === 'in' ? '入库' : '出库' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="quantity" label="数量" width="70" align="center" />
            <el-table-column label="时间" width="110">
              <template #default="{ row }">
                <span class="muted">{{ (row.created_at || '').replace('T', ' ').slice(0, 10) }}</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import http from '../api'

const router = useRouter()

const totalComponents = ref(0)
const lowStockCount = ref(0)
const recent = ref([])
const recentExpenses = ref([])
const household = ref({
  months: [], utility: 0, expense: 0, thisMonth: 0, thisMonthUtility: 0, thisMonthExpense: 0
})

const trendRef = ref()
let trendChart = null

function fmtMoney(value) {
  return Number(value || 0).toFixed(2)
}

const cards = computed(() => [
  {
    label: '本月家庭支出',
    value: `¥${fmtMoney(household.value.thisMonth)}`,
    sub: `缴费 ${fmtMoney(household.value.thisMonthUtility)} · 开支 ${fmtMoney(household.value.thisMonthExpense)}`
  },
  {
    label: '近 6 月家庭支出',
    value: `¥${fmtMoney(household.value.utility + household.value.expense)}`,
    sub: `缴费 ${fmtMoney(household.value.utility)} · 开支 ${fmtMoney(household.value.expense)}`
  },
  { label: '物料总数', value: totalComponents.value, sub: '电子元器件与家用备件' },
  { label: '低库存物料', value: lowStockCount.value, danger: true, sub: '需要补货' }
])

function go(path) {
  router.push(path)
}

async function load() {
  const [componentsRes, lowStockRes, transactionsRes, expenseStats, expenseList, utilityStats] =
    await Promise.all([
      http.get('/components', { params: { page: 1, per_page: 1 } }),
      http.get('/components/low-stock'),
      http.get('/transactions', { params: { page: 1, per_page: 5 } }),
      http.get('/expenses/stats', { params: { months: 6 } }),
      http.get('/expenses', { params: { page: 1, per_page: 5 } }),
      http.get('/utility-bills/stats', { params: { months: 6 } })
    ])

  totalComponents.value = componentsRes.data.total
  lowStockCount.value = lowStockRes.data.length
  recent.value = transactionsRes.data.items
  recentExpenses.value = expenseList.data.items

  const expMonthly = expenseStats.data.monthly || []
  const utilMonthly = utilityStats.data.monthly || []
  // 两个接口用同一个 months 参数、同样零填充到当月，月份标签天然对齐
  const months = expMonthly.map((m) => m.month)
  const lastIndex = expMonthly.length - 1
  const thisMonthExpense = expMonthly[lastIndex]?.amount ?? 0
  const thisMonthUtility = utilMonthly[lastIndex]?.amount ?? 0

  household.value = {
    months,
    expense: expenseStats.data.total ?? 0,
    utility: utilityStats.data.total ?? 0,
    thisMonthExpense,
    thisMonthUtility,
    thisMonth: thisMonthExpense + thisMonthUtility
  }

  await nextTick()
  renderTrend(months, utilMonthly.map((m) => m.amount), expMonthly.map((m) => m.amount))
}

function renderTrend(months, utility, expense) {
  if (!trendRef.value) return
  trendChart = trendChart || echarts.init(trendRef.value)
  trendChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 55, right: 20, top: 26, bottom: 36 },
    legend: { show: false },
    xAxis: { type: 'category', data: months },
    yAxis: { type: 'value', name: '元' },
    series: [
      {
        name: '缴费', type: 'bar', stack: 'total', barMaxWidth: 42,
        itemStyle: { color: '#409eff', borderRadius: [0, 0, 0, 0] },
        data: utility
      },
      {
        name: '开支', type: 'bar', stack: 'total', barMaxWidth: 42,
        itemStyle: { color: '#f56c6c', borderRadius: [4, 4, 0, 0] },
        data: expense
      }
    ]
  }, true)
}

function resizeChart() {
  trendChart?.resize()
}

onMounted(async () => {
  await load()
  window.addEventListener('resize', resizeChart)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeChart)
  trendChart?.dispose()
})
</script>

<style scoped>
.stat {
  text-align: center;
  padding: 8px 0;
}

.value {
  font-size: 26px;
  font-weight: 700;
  color: #1677ff;
}

.value.danger {
  color: #f56c6c;
}

.label {
  margin-top: 8px;
  color: #606266;
  font-size: 13px;
}

.sub {
  margin-top: 4px;
  color: #a8abb2;
  font-size: 12px;
  min-height: 16px;
}

.mt {
  margin-top: 16px;
}

.chart {
  height: 260px;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.legend {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #909399;
  font-size: 12px;
  font-weight: 400;
}

.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 2px;
}

.dot.utility {
  background: #409eff;
  margin-left: 4px;
}

.dot.expense {
  background: #f56c6c;
  margin-left: 8px;
}

.money {
  color: #f56c6c;
  font-weight: 600;
}

.muted {
  color: #909399;
}

.stat-row {
  row-gap: 16px;
}
</style>
