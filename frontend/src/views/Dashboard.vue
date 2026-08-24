<template>
  <div>
    <el-row :gutter="16" class="stat-row">
      <el-col :span="8" v-for="card in cards" :key="card.label">
        <el-card shadow="hover">
          <div class="stat">
            <div class="value" :class="{ danger: card.danger }">{{ card.value }}</div>
            <div class="label">{{ card.label }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="recent">
      <template #header>最近流水</template>
      <el-table :data="recent" border stripe>
        <el-table-column prop="created_at" label="时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="component_name" label="物料" min-width="160" />
        <el-table-column label="类型" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.type === 'in' ? 'success' : 'danger'">
              {{ row.type === 'in' ? '入库' : '出库' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="quantity" label="数量" width="90" align="center" />
        <el-table-column prop="operator_name" label="操作人" width="120" />
        <el-table-column prop="note" label="备注" min-width="160" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import http from '../api'

const totalComponents = ref(0)
const lowStockCount = ref(0)
const totalTransactions = ref(0)
const totalInCost = ref(0)
const totalOutQty = ref(0)
const inventoryValue = ref(0)
const recent = ref([])

function formatTime(value) {
  return value ? value.replace('T', ' ').slice(0, 19) : ''
}

function fmtMoney(value) {
  return Number(value || 0).toFixed(2)
}

const cards = computed(() => [
  { label: '物料总数', value: totalComponents.value },
  { label: '低库存物料', value: lowStockCount.value, danger: true },
  { label: '累计采购金额(元)', value: fmtMoney(totalInCost.value) },
  { label: '累计消耗数量', value: totalOutQty.value },
  { label: '当前库存估值(元)', value: fmtMoney(inventoryValue.value) },
  { label: '流水记录', value: totalTransactions.value }
])

async function load() {
  const [componentsRes, lowStockRes, transactionsRes, overviewRes] = await Promise.all([
    http.get('/components', { params: { page: 1, per_page: 1 } }),
    http.get('/components/low-stock'),
    http.get('/transactions', { params: { page: 1, per_page: 5 } }),
    http.get('/stats/overview')
  ])
  totalComponents.value = componentsRes.data.total
  lowStockCount.value = lowStockRes.data.length
  totalTransactions.value = transactionsRes.data.total
  recent.value = transactionsRes.data.items
  totalInCost.value = overviewRes.data.total_in_cost
  totalOutQty.value = overviewRes.data.total_out_qty
  inventoryValue.value = overviewRes.data.inventory_value
}

onMounted(load)
</script>

<style scoped>
.stat {
  text-align: center;
  padding: 8px 0;
}

.value {
  font-size: 28px;
  font-weight: 700;
  color: #1677ff;
}

.value.danger {
  color: #f56c6c;
}

.label {
  margin-top: 8px;
  color: #909399;
}

.recent {
  margin-top: 16px;
}

.stat-row {
  row-gap: 16px;
}
</style>
