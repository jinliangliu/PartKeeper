<template>
  <div>
    <div class="toolbar">
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        value-format="YYYY-MM-DD"
        style="width: 280px"
      />
      <el-button type="primary" @click="applyRange">应用</el-button>
      <el-button @click="resetRange">全部时间</el-button>
      <div class="spacer" />
      <el-button type="success" @click="exportCsv">导出 CSV</el-button>
    </div>

    <el-row :gutter="16" class="stat-row">
      <el-col :span="4" v-for="card in cards" :key="card.label">
        <el-card shadow="hover">
          <div class="stat">
            <div class="value" :class="{ danger: card.danger }">{{ card.value }}</div>
            <div class="label">{{ card.label }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="16">
        <el-card shadow="never">
          <template #header>月度采购 / 消耗趋势</template>
          <div ref="trendRef" class="chart chart-lg"></div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>供应商采购金额占比</template>
          <div ref="supplierRef" class="chart chart-lg"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>采购金额 Top 组件</template>
          <div ref="purchaseTopRef" class="chart chart-lg"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>消耗数量 Top 组件</template>
          <div ref="consumptionTopRef" class="chart chart-lg"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="mt">
      <template #header>分类采购金额分布</template>
      <div ref="categoryRef" class="chart chart-lg"></div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import * as echarts from 'echarts'
import http from '../api'

const overview = ref({})
const trend = ref([])
const purchasesComponent = ref([])
const purchasesSupplier = ref([])
const purchasesCategory = ref([])
const consumptionComponent = ref([])

const trendRef = ref()
const supplierRef = ref()
const purchaseTopRef = ref()
const consumptionTopRef = ref()
const categoryRef = ref()
const dateRange = ref([])
const filters = reactive({ start: '', end: '' })

let charts = []

const cards = computed(() => [
  { label: '累计采购金额(元)', value: fmt(overview.value.total_in_cost) },
  { label: '累计采购数量', value: overview.value.total_in_qty ?? '-' },
  { label: '累计消耗数量', value: overview.value.total_out_qty ?? '-' },
  { label: '当前库存估值(元)', value: fmt(overview.value.inventory_value) },
  { label: '物料总数', value: overview.value.total_components ?? '-' },
  { label: '低库存物料', value: overview.value.low_stock_count ?? '-', danger: true }
])

function fmt(value) {
  if (value == null) return '-'
  return Number(value).toFixed(2)
}

function rangeParams() {
  const params = {}
  if (filters.start) params.start = filters.start
  if (filters.end) params.end = filters.end
  return params
}

async function load() {
  const range = rangeParams()
  const [overviewRes, trendRes, pcRes, psRes, pcatRes, ccRes] = await Promise.all([
    http.get('/stats/overview', { params: range }),
    http.get('/stats/trend', { params: { ...range, months: 12 } }),
    http.get('/stats/purchases', { params: { ...range, group: 'component', limit: 10 } }),
    http.get('/stats/purchases', { params: { ...range, group: 'supplier', limit: 10 } }),
    http.get('/stats/purchases', { params: { ...range, group: 'category', limit: 10 } }),
    http.get('/stats/consumption', { params: { ...range, group: 'component', limit: 10 } })
  ])
  overview.value = overviewRes.data
  trend.value = trendRes.data
  purchasesComponent.value = pcRes.data
  purchasesSupplier.value = psRes.data
  purchasesCategory.value = pcatRes.data
  consumptionComponent.value = ccRes.data
  renderCharts()
}

function applyRange() {
  filters.start = dateRange.value?.[0] || ''
  filters.end = dateRange.value?.[1] || ''
  load()
}

function resetRange() {
  dateRange.value = []
  filters.start = ''
  filters.end = ''
  load()
}

async function exportCsv() {
  const blob = await http.get('/stats/export', { params: rangeParams(), responseType: 'blob' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'purchase_consumption_stats.csv'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

function renderCharts() {
  charts.forEach((c) => c.dispose())
  charts = []

  const trendChart = echarts.init(trendRef.value)
  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['采购金额(元)', '入库数量', '出库数量'] },
    grid: { left: 50, right: 50, bottom: 30, top: 40 },
    xAxis: { type: 'category', data: trend.value.map((t) => t.month) },
    yAxis: [
      { type: 'value', name: '金额' },
      { type: 'value', name: '数量' }
    ],
    series: [
      {
        name: '采购金额(元)', type: 'line', yAxisIndex: 0, smooth: true,
        data: trend.value.map((t) => t.in_cost)
      },
      {
        name: '入库数量', type: 'bar', yAxisIndex: 1,
        data: trend.value.map((t) => t.in_qty)
      },
      {
        name: '出库数量', type: 'bar', yAxisIndex: 1,
        data: trend.value.map((t) => t.out_qty)
      }
    ]
  })
  charts.push(trendChart)

  const supplierChart = echarts.init(supplierRef.value)
  supplierChart.setOption({
    tooltip: { trigger: 'item' },
    legend: { type: 'scroll', orient: 'vertical', right: 0, top: 20 },
    series: [{
      type: 'pie', radius: ['40%', '70%'],
      data: purchasesSupplier.value.map((s) => ({ name: s.name, value: s.cost }))
    }]
  })
  charts.push(supplierChart)

  const purchaseTopChart = echarts.init(purchaseTopRef.value)
  purchaseTopChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 130, right: 30, bottom: 30, top: 20 },
    xAxis: { type: 'value', name: '元' },
    yAxis: { type: 'category', inverse: true, data: purchasesComponent.value.map((p) => p.name).reverse() },
    series: [{
      type: 'bar', barMaxWidth: 22,
      data: purchasesComponent.value.map((p) => p.cost).reverse()
    }]
  })
  charts.push(purchaseTopChart)

  const consumptionTopChart = echarts.init(consumptionTopRef.value)
  consumptionTopChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 130, right: 30, bottom: 30, top: 20 },
    xAxis: { type: 'value', name: '个' },
    yAxis: { type: 'category', inverse: true, data: consumptionComponent.value.map((c) => c.name).reverse() },
    series: [{
      type: 'bar', barMaxWidth: 22,
      data: consumptionComponent.value.map((c) => c.quantity).reverse()
    }]
  })
  charts.push(consumptionTopChart)

  const categoryChart = echarts.init(categoryRef.value)
  categoryChart.setOption({
    tooltip: { trigger: 'item' },
    legend: { type: 'scroll', bottom: 0 },
    series: [{
      type: 'pie', radius: '60%',
      data: purchasesCategory.value.map((c) => ({ name: c.name, value: c.cost }))
    }]
  })
  charts.push(categoryChart)
}

function handleResize() {
  charts.forEach((c) => c.resize())
}

onMounted(() => {
  load()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  charts.forEach((c) => c.dispose())
})
</script>

<style scoped>
.stat-row {
  margin-bottom: 16px;
}

.stat {
  text-align: center;
}

.value {
  font-size: 24px;
  font-weight: 700;
  color: #1677ff;
}

.value.danger {
  color: #f56c6c;
}

.label {
  margin-top: 6px;
  color: #909399;
  font-size: 13px;
}

.chart {
  width: 100%;
}

.chart-lg {
  height: 320px;
}

.mt {
  margin-top: 16px;
}
</style>
