<template>
  <div class="page-card">
    <el-alert
      title="低库存预警"
      description="以下物料的当前库存已低于或等于最低库存阈值，请及时补货。"
      type="warning"
      show-icon
      :closable="false"
      style="margin-bottom: 16px"
    />

    <el-table :data="items" v-loading="loading" border stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="名称" min-width="140" />
      <el-table-column prop="value" label="值" width="110" />
      <el-table-column label="当前库存" width="120" align="center">
        <template #default="{ row }">
          <el-tag type="danger">{{ row.current_stock }} {{ row.unit }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="min_stock" label="最低库存" width="110" align="center" />
      <el-table-column prop="location" label="库位" width="120" />
      <el-table-column label="操作" width="120" fixed="right">
        <template #default>
          <el-button link type="primary" @click="$router.push('/stock-in')">去入库</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import http from '../api'

const loading = ref(false)
const items = ref([])

async function load() {
  loading.value = true
  try {
    const res = await http.get('/components/low-stock')
    items.value = res.data
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
