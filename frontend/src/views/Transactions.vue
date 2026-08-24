<template>
  <div class="page-card">
    <div class="toolbar">
      <el-select
        v-model="query.component_id"
        filterable
        remote
        clearable
        :remote-method="searchComponents"
        :loading="searching"
        placeholder="按物料筛选"
        style="width: 240px"
        @change="reload"
      >
        <el-option v-for="c in componentOptions" :key="c.id" :label="c.label" :value="c.id" />
      </el-select>
      <el-select v-model="query.type" placeholder="操作类型" clearable style="width: 140px" @change="reload">
        <el-option label="入库" value="in" />
        <el-option label="出库" value="out" />
      </el-select>
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        value-format="YYYY-MM-DD"
        style="width: 260px"
        @change="reload"
      />
      <el-button type="primary" @click="reload">查询</el-button>
    </div>

    <el-table :data="items" v-loading="loading" border stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="created_at" label="时间" width="180">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column prop="component_name" label="物料" min-width="150" />
      <el-table-column label="类型" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="row.type === 'in' ? 'success' : 'danger'">
            {{ row.type === 'in' ? '入库' : '出库' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="quantity" label="数量" width="90" align="center" />
      <el-table-column label="单价(元)" width="100" align="right">
        <template #default="{ row }">
          <span v-if="row.unit_price != null">{{ row.unit_price }}</span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="金额(元)" width="100" align="right">
        <template #default="{ row }">
          <span v-if="row.unit_price != null">{{ (row.quantity * row.unit_price).toFixed(2) }}</span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="operator_name" label="操作人" width="120" />
      <el-table-column prop="note" label="备注" min-width="180" />
    </el-table>

    <div class="pager">
      <el-pagination
        v-model:current-page="query.page"
        v-model:page-size="query.per_page"
        :total="total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        @current-change="load"
        @size-change="reload"
      />
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import http from '../api'

const loading = ref(false)
const searching = ref(false)
const items = ref([])
const total = ref(0)
const componentOptions = ref([])
const dateRange = ref([])
const query = reactive({ page: 1, per_page: 20, component_id: null, type: null, start: '', end: '' })

function formatTime(value) {
  return value ? value.replace('T', ' ').slice(0, 19) : ''
}

async function searchComponents(keyword = '') {
  searching.value = true
  try {
    const res = await http.get('/components', { params: { page: 1, per_page: 50, keyword } })
    componentOptions.value = res.data.items.map((c) => ({
      id: c.id,
      label: `${c.name}${c.value ? ` · ${c.value}` : ''}`
    }))
  } finally {
    searching.value = false
  }
}

async function load() {
  loading.value = true
  try {
    const params = { page: query.page, per_page: query.per_page }
    if (query.component_id) params.component_id = query.component_id
    if (query.type) params.type = query.type
    if (dateRange.value?.[0]) params.start = dateRange.value[0]
    if (dateRange.value?.[1]) params.end = dateRange.value[1]
    const res = await http.get('/transactions', { params })
    items.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function reload() {
  query.page = 1
  load()
}

onMounted(() => {
  searchComponents('')
  load()
})
</script>

<style scoped>
.pager {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
