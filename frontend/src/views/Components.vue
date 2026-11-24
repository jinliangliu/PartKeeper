<template>
  <div class="page-card">
    <div class="toolbar">
      <el-input
        v-model="query.keyword"
        :placeholder="semanticMode ? '描述要找的东西，如「十千欧的贴片电阻」' : '搜索名称 / 值 / 封装 / 品牌'"
        clearable
        style="width: 300px"
        @keyup.enter="load"
        @clear="load"
      />
      <el-tooltip
        content="按参数语义检索，支持「一百微法的电容」这类描述；需服务端启用 PostgreSQL + pgvector"
        placement="top"
      >
        <el-switch v-model="semanticMode" active-text="语义" @change="onSemanticToggle" />
      </el-tooltip>
      <el-select v-model="query.category_id" placeholder="分类" clearable style="width: 160px" @change="load">
        <el-option v-for="c in categoryOptions" :key="c.value" :label="c.label" :value="c.value" />
      </el-select>
      <el-button type="primary" @click="load">查询</el-button>
      <div class="spacer" />
      <el-button v-if="authStore.isAdmin" @click="openBom">BOM 导入</el-button>
      <el-button v-if="authStore.isAdmin" type="success" @click="openCreate">新增物品</el-button>
    </div>

    <div v-if="selectedIds.length" class="batch-bar">
      <span>已选 <b>{{ selectedIds.length }}</b> 项</span>
      <el-select v-model="batchKind" placeholder="设为类型" size="small" style="width: 140px">
        <el-option v-for="k in KIND_OPTIONS" :key="k.value" :label="k.label" :value="k.value" />
      </el-select>
      <el-button
        type="primary"
        size="small"
        :disabled="!batchKind"
        :loading="batchSaving"
        @click="applyBatchKind"
      >
        应用
      </el-button>
      <el-button size="small" @click="clearSelection">取消选择</el-button>
      <span class="muted batch-hint">只改类型，原 值/封装 等信息保留</span>
    </div>

    <el-table
      ref="tableRef"
      :data="items"
      v-loading="loading"
      border
      stripe
      @selection-change="onSelectionChange"
    >
      <el-table-column v-if="authStore.isAdmin" type="selection" width="44" />
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column v-if="semanticMode" label="相似度" width="90" align="center">
        <template #default="{ row }">
          <el-tag
            v-if="row.score != null"
            size="small"
            effect="plain"
            :type="row.score >= 0.55 ? 'success' : 'info'"
          >
            {{ Math.round(row.score * 100) }}%
          </el-tag>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="112" align="center">
        <template #default="{ row }">
          <el-dropdown
            v-if="authStore.isAdmin"
            trigger="click"
            @command="(k) => quickChangeKind(row, k)"
          >
            <el-tag size="small" effect="plain" class="kind-tag">{{ kindLabel(row.kind) }}</el-tag>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="k in KIND_OPTIONS"
                  :key="k.value"
                  :command="k.value"
                  :disabled="k.value === row.kind"
                >
                  {{ k.label }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-tag v-else size="small" effect="plain">{{ kindLabel(row.kind) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="名称" min-width="120" />
      <el-table-column prop="value" label="值" min-width="90" />
      <el-table-column prop="package" label="封装" width="90" />
      <el-table-column prop="brand" label="品牌" width="100" />
      <el-table-column prop="category" label="分类" width="100" />
      <el-table-column label="库存" width="120" align="center">
        <template #default="{ row }">
          <el-tag :type="row.current_stock <= row.min_stock ? 'danger' : 'success'">
            {{ row.current_stock }} {{ row.unit }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="min_stock" label="最低库存" width="90" align="center" />
      <el-table-column prop="location" label="库位" width="100" />
      <el-table-column prop="supplier" label="供应商" width="120" />
      <el-table-column label="家庭属性" width="150">
        <template #default="{ row }">
          <div class="home-tags">
            <el-tag v-if="row.is_consumable" size="small" type="warning" effect="plain">消耗品</el-tag>
            <el-tag v-if="warrantyState(row) === 'expired'" size="small" type="danger" effect="plain">
              已过保
            </el-tag>
            <el-tag v-else-if="warrantyState(row) === 'soon'" size="small" type="warning" effect="plain">
              将过保
            </el-tag>
            <el-tag v-else-if="warrantyState(row) === 'active'" size="small" type="success" effect="plain">
              保修中
            </el-tag>
            <el-tag v-if="maintenanceOverdue(row)" size="small" type="danger" effect="plain">待维护</el-tag>
            <span v-if="!hasHomeInfo(row)" class="muted">—</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openMaintenance(row)">维护</el-button>
          <el-button v-if="authStore.isAdmin" link type="primary" @click="openEdit(row.id)">编辑</el-button>
          <el-button v-if="authStore.isAdmin" link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination
        v-if="!semanticMode"
        v-model:current-page="query.page"
        v-model:page-size="query.per_page"
        :total="total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        @current-change="load"
        @size-change="load"
      />
      <span v-else class="muted">语义检索按相似度排序，最多返回 20 条</span>
    </div>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑物品' : '新增物品'" width="720px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="名称" prop="name"><el-input v-model="form.name" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="类型">
              <el-select v-model="form.kind" style="width: 100%">
                <el-option v-for="k in KIND_OPTIONS" :key="k.value" :label="k.label" :value="k.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <template v-if="form.kind === 'electronic'">
            <el-col :span="12">
              <el-form-item label="值"><el-input v-model="form.value" /></el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="封装"><el-input v-model="form.package" /></el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="精度"><el-input v-model="form.tolerance" /></el-form-item>
            </el-col>
          </template>
          <el-col :span="12">
            <el-form-item label="品牌"><el-input v-model="form.brand" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="单位">
              <el-input v-model="form.unit" placeholder="个" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="分类">
              <el-select v-model="form.category_id" placeholder="选择分类" clearable style="width: 100%">
                <el-option v-for="c in categoryOptions" :key="c.value" :label="c.label" :value="c.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="库位">
              <el-select v-model="form.location_id" placeholder="选择库位" clearable style="width: 100%">
                <el-option v-for="l in locations" :key="l.id" :label="l.name" :value="l.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="供应商">
              <el-select v-model="form.supplier_id" placeholder="选择供应商" clearable style="width: 100%">
                <el-option v-for="s in suppliers" :key="s.id" :label="s.name" :value="s.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="最低库存">
              <el-input-number v-model="form.min_stock" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col v-if="!editingId" :span="12">
            <el-form-item label="当前库存">
              <el-input-number v-model="form.current_stock" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col v-if="form.kind === 'electronic'" :span="24">
            <el-form-item label="Datasheet">
              <el-input v-model="form.datasheet_url" placeholder="数据手册链接" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">家庭属性（可选）</el-divider>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="消耗品">
              <el-switch v-model="form.is_consumable" />
              <span class="field-hint">会消耗、需要定期补货</span>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="消耗速率">
              <el-input-number v-model="form.consumption_rate" :min="0" :precision="2" :step="0.5"
                               controls-position="right" placeholder="单位/天"
                               :disabled="!form.is_consumable" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="保修到期">
              <el-date-picker v-model="form.warranty_expiry" type="date" value-format="YYYY-MM-DD"
                              placeholder="购买保修截止日" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="维护周期">
              <el-input-number v-model="form.maintenance_cycle_days" :min="0" :step="30"
                               controls-position="right" placeholder="天数"
                               style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="上次维护">
              <el-date-picker v-model="form.last_maintenance_date" type="date" value-format="YYYY-MM-DD"
                              placeholder="填了才会算下次维护日" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label-width="100px">
              <span class="field-hint">
                维护提醒 = 上次维护日期 + 维护周期；消耗速率留空则由出库流水推算
              </span>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="bomDialogVisible" title="BOM 导入" width="860px">
      <el-alert
        title="支持常见 EDA 导出的 CSV 物料清单"
        description="表头需包含“值/Value”列，建议同时包含“封装/Package”和“数量/Qty”。系统会与现有物料匹配，标出缺失与缺口。"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      />

      <el-upload
        drag
        :auto-upload="false"
        :limit="1"
        accept=".csv"
        :on-change="handleBomFileChange"
        :on-remove="handleBomFileRemove"
      >
        <div class="el-upload__text">将 CSV 文件拖到此处，或 <em>点击选择文件</em></div>
      </el-upload>

      <template v-if="bomResult">
        <div class="bom-summary">
          <el-tag>共 {{ bomResult.summary.total_lines }} 行</el-tag>
          <el-tag type="success">已匹配 {{ bomResult.summary.matched_lines }}</el-tag>
          <el-tag type="warning">缺失物料 {{ bomResult.summary.missing_lines }}</el-tag>
          <el-tag type="danger">总缺口 {{ bomResult.summary.total_shortage_qty }}</el-tag>
        </div>

        <el-table :data="bomResult.lines" border size="small" max-height="360">
          <el-table-column prop="row" label="行" width="50" />
          <el-table-column prop="designator" label="位号" width="100" />
          <el-table-column prop="value" label="值" min-width="110" />
          <el-table-column prop="package" label="封装" width="100" />
          <el-table-column prop="quantity" label="数量" width="70" align="center" />
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.matched_id" type="success" size="small">已匹配</el-tag>
              <el-tag v-else type="warning" size="small">缺失</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="current_stock" label="当前库存" width="90" align="center" />
          <el-table-column label="缺口" width="80" align="center">
            <template #default="{ row }">
              <span :class="{ 'text-danger': row.shortage > 0 }">{{ row.shortage }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="matched_name" label="匹配物料" min-width="130" />
        </el-table>
      </template>

      <template #footer>
        <el-button @click="closeBom">取消</el-button>
        <el-button type="primary" :loading="bomLoading" @click="parseBom">解析预览</el-button>
        <el-button
          v-if="bomResult && authStore.isAdmin"
          type="success"
          :loading="bomApplying"
          @click="applyBom"
        >
          创建缺失物料
        </el-button>
      </template>
    </el-dialog>

    <!-- 维护记录与持有账本 -->
    <el-drawer v-model="maintVisible" :title="`维护 · ${maintTarget?.name || ''}`" size="640px">
      <div v-loading="maintLoading" class="maint-body">
        <el-row :gutter="12" class="ledger-cards">
          <el-col :span="6">
            <div class="ledger-card">
              <div class="lv">¥{{ ledger.total_spent ?? 0 }}</div>
              <div class="ll">总投入</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="ledger-card">
              <div class="lv">¥{{ ledger.purchase_total ?? 0 }}</div>
              <div class="ll">购置（{{ ledger.purchase_count ?? 0 }} 笔）</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="ledger-card">
              <div class="lv">¥{{ ledger.maintenance_total ?? 0 }}</div>
              <div class="ll">维修保养</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="ledger-card">
              <div class="lv">{{ ledger.annual_cost != null ? `¥${ledger.annual_cost}` : '—' }}</div>
              <div class="ll">年均成本</div>
            </div>
          </el-col>
        </el-row>

        <div class="ledger-meta">
          <el-tag v-if="ledger.warranty_days_left != null" size="small"
                  :type="ledger.warranty_days_left < 0 ? 'danger' : (ledger.warranty_days_left <= 30 ? 'warning' : 'success')"
                  effect="plain">
            {{ ledger.warranty_days_left < 0 ? `已过保 ${-ledger.warranty_days_left} 天`
               : `保修剩 ${ledger.warranty_days_left} 天` }}
          </el-tag>
          <el-tag v-if="ledger.next_maintenance_due" size="small"
                  :type="ledger.maintenance_overdue ? 'danger' : 'info'" effect="plain">
            {{ ledger.maintenance_overdue ? '维护已逾期' : '下次维护' }} {{ ledger.next_maintenance_due }}
          </el-tag>
          <span v-if="ledger.days_owned" class="muted">持有 {{ ledger.days_owned }} 天</span>
          <span v-if="ledger.maintenance_record_count" class="muted">
            维护 {{ ledger.maintenance_record_count }} 次
          </span>
        </div>

        <el-divider content-position="left">新增维护记录</el-divider>
        <el-form :model="maintForm" label-width="80px" class="maint-form">
          <el-row :gutter="12">
            <el-col :span="12">
              <el-form-item label="类型">
                <el-select v-model="maintForm.type" style="width: 100%">
                  <el-option v-for="t in maintMeta.types" :key="t.value" :label="t.label" :value="t.value" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="日期">
                <el-date-picker v-model="maintForm.performed_at" type="date" value-format="YYYY-MM-DD"
                                style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="24">
              <el-form-item label="内容" required>
                <el-input v-model="maintForm.title" placeholder="换了 HEPA 滤芯 / 清洗冷凝器 / 主板维修" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="花费">
                <el-input-number v-model="maintForm.cost" :min="0" :precision="2" :step="50"
                                 controls-position="right" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="渠道">
                <el-select v-model="maintForm.channel" style="width: 100%">
                  <el-option v-for="c in maintMeta.channels" :key="c.value" :label="c.label" :value="c.value" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="服务商">
                <el-input v-model="maintForm.vendor" placeholder="维修点 / 平台" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="备注">
                <el-input v-model="maintForm.note" />
              </el-form-item>
            </el-col>
            <el-col :span="24">
              <el-form-item label-width="80px">
                <div class="maint-submit">
                  <el-button type="primary" :loading="maintSaving" @click="submitMaintenance">保存维护记录</el-button>
                  <span class="field-hint">
                    花费 &gt; 0 会自动生成一笔「维修保养」开支并挂到本物品；维护日期会更新上次维护日
                  </span>
                </div>
              </el-form-item>
            </el-col>
          </el-row>
        </el-form>

        <el-divider content-position="left">维护历史</el-divider>
        <el-empty v-if="!ledger.records?.length" description="还没有维护记录" :image-size="60" />
        <el-timeline v-else>
          <el-timeline-item v-for="rec in ledger.records" :key="rec.id"
                            :timestamp="rec.performed_at" placement="top">
            <div class="maint-item">
              <div class="maint-head">
                <el-tag size="small" effect="plain">{{ rec.type_label }}</el-tag>
                <span class="maint-title">{{ rec.title }}</span>
                <span v-if="rec.cost > 0" class="amount">¥{{ rec.cost }}</span>
                <el-button link type="danger" size="small" @click="removeMaintenance(rec)">删除</el-button>
              </div>
              <div class="maint-sub">
                <span v-if="rec.vendor">{{ rec.vendor }}</span>
                <span v-if="rec.note">{{ rec.note }}</span>
                <span v-if="!rec.expense_id && rec.cost === 0" class="muted">未产生费用</span>
              </div>
            </div>
          </el-timeline-item>
        </el-timeline>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '../api'
import { authStore } from '../stores/auth'

const loading = ref(false)
const saving = ref(false)
const items = ref([])
const total = ref(0)
const query = reactive({ page: 1, per_page: 20, keyword: '', category_id: null })
// 语义模式：走 /components/semantic-search，按向量相似度排序，不分页
const semanticMode = ref(false)

const dialogVisible = ref(false)
const editingId = ref(null)
const formRef = ref()
const KIND_OPTIONS = [
  { value: 'electronic', label: '电子元器件' },
  { value: 'appliance', label: '家电' },
  { value: 'furniture', label: '家具' },
  { value: 'vehicle', label: '车辆' },
  { value: 'other', label: '其他' }
]

const kindLabel = (k) => KIND_OPTIONS.find((o) => o.value === k)?.label || k || '—'

const form = reactive({
  kind: 'electronic',
  name: '', value: '', package: '', tolerance: '', brand: '', unit: '个',
  category_id: null, location_id: null, supplier_id: null,
  min_stock: 0, current_stock: 0, datasheet_url: '',
  is_consumable: false, consumption_rate: null, warranty_expiry: '',
  maintenance_cycle_days: null, last_maintenance_date: ''
})
const rules = { name: [{ required: true, message: '请输入物料名称', trigger: 'blur' }] }

// --- 家庭属性：与 MCP 的 list_expiring_warranties 保持同一套判定 ---
const SOON_DAYS = 30

function daysUntil(dateStr) {
  if (!dateStr) return null
  const target = new Date(`${dateStr}T00:00:00`)
  if (Number.isNaN(target.getTime())) return null
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.round((target - today) / 86400000)
}

function warrantyState(row) {
  const days = daysUntil(row.warranty_expiry)
  if (days === null) return ''
  if (days < 0) return 'expired'
  return days <= SOON_DAYS ? 'soon' : 'active'
}

function maintenanceOverdue(row) {
  if (!row.last_maintenance_date || !row.maintenance_cycle_days) return false
  const elapsed = daysUntil(row.last_maintenance_date)
  if (elapsed === null) return false
  return -elapsed >= row.maintenance_cycle_days
}

function hasHomeInfo(row) {
  return Boolean(
    row.is_consumable || row.warranty_expiry || row.maintenance_cycle_days || row.last_maintenance_date
  )
}

const categoryOptions = ref([])
const suppliers = ref([])
const locations = ref([])

const bomDialogVisible = ref(false)
const bomFile = ref(null)
const bomLoading = ref(false)
const bomApplying = ref(false)
const bomResult = ref(null)

function flattenCategories(nodes, depth = 0, out = []) {
  for (const node of nodes) {
    out.push({ value: node.id, label: `${'　'.repeat(depth)}${node.name}` })
    if (node.children?.length) {
      flattenCategories(node.children, depth + 1, out)
    }
  }
  return out
}

async function loadMeta() {
  const [catRes, supRes, locRes] = await Promise.all([
    http.get('/categories'),
    http.get('/suppliers'),
    http.get('/locations')
  ])
  categoryOptions.value = flattenCategories(catRes.data)
  suppliers.value = supRes.data
  locations.value = locRes.data
}

async function load() {
  loading.value = true
  try {
    if (semanticMode.value) {
      if (!query.keyword) {
        items.value = []
        total.value = 0
        return
      }
      const params = { q: query.keyword, limit: 20 }
      if (query.category_id) params.category_id = query.category_id
      const res = await http.get('/components/semantic-search', { params })
      items.value = res.data.items
      total.value = res.data.total
      return
    }

    const params = { page: query.page, per_page: query.per_page }
    if (query.keyword) params.keyword = query.keyword
    if (query.category_id) params.category_id = query.category_id
    const res = await http.get('/components', { params })
    items.value = res.data.items
    total.value = res.data.total
  } catch (e) {
    // 服务端没启用语义能力时自动退回关键词模式，别让用户卡在不可用的开关上
    if (semanticMode.value && e?.response?.status === 503) {
      semanticMode.value = false
      await load()
    }
  } finally {
    loading.value = false
  }
}

function onSemanticToggle(enabled) {
  query.page = 1
  if (enabled && !query.keyword) {
    ElMessage.info('语义模式：输入一句描述，例如「一百微法的电解电容」')
  }
  load()
}

// --- 类型快速修改 ---

const tableRef = ref()
const selectedIds = ref([])
const batchKind = ref('')
const batchSaving = ref(false)

function onSelectionChange(rows) {
  selectedIds.value = rows.map((r) => r.id)
}

function clearSelection() {
  tableRef.value?.clearSelection()
  selectedIds.value = []
  batchKind.value = ''
}

async function quickChangeKind(row, kind) {
  if (!kind || kind === row.kind) return
  try {
    await http.put(`/components/${row.id}`, { kind })
    ElMessage.success(`已设为${kindLabel(kind)}`)
    await load()
  } catch (e) {
    // 失败时不做本地赋值，列表保持服务端真实状态
  }
}

async function applyBatchKind() {
  if (!selectedIds.value.length || !batchKind.value) return
  batchSaving.value = true
  try {
    const res = await http.post('/components/batch-kind', {
      ids: selectedIds.value,
      kind: batchKind.value
    })
    const d = res.data || {}
    let msg = `已将 ${d.matched ?? selectedIds.value.length} 项设为${kindLabel(batchKind.value)}`
    if (d.changed !== d.matched) msg += `（${d.matched - d.changed} 项原本就是该类型）`
    if (d.missing?.length) msg += `，${d.missing.length} 项已不存在`
    ElMessage.success(msg)
    clearSelection()
    await load()
  } finally {
    batchSaving.value = false
  }
}

function resetForm() {
  Object.assign(form, {
    kind: 'electronic',
    name: '', value: '', package: '', tolerance: '', brand: '', unit: '个',
    category_id: null, location_id: null, supplier_id: null,
    min_stock: 0, current_stock: 0, datasheet_url: '',
    is_consumable: false, consumption_rate: null, warranty_expiry: '',
    maintenance_cycle_days: null, last_maintenance_date: ''
  })
}

function openCreate() {
  editingId.value = null
  resetForm()
  dialogVisible.value = true
}

async function openEdit(id) {
  const res = await http.get(`/components/${id}`)
  Object.assign(form, res.data)
  form.kind = res.data.kind || 'electronic'
  editingId.value = id
  dialogVisible.value = true
}

async function save() {
  await formRef.value.validate()
  saving.value = true
  try {
    if (editingId.value) {
      await http.put(`/components/${editingId.value}`, form)
      ElMessage.success('更新成功')
    } else {
      await http.post('/components', form)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确定删除物料「${row.name}」吗？`, '警告', { type: 'warning' })
  await http.delete(`/components/${row.id}`)
  ElMessage.success('删除成功')
  load()
}

// --- 维护记录与持有账本 ---
const maintVisible = ref(false)
const maintLoading = ref(false)
const maintSaving = ref(false)
const maintTarget = ref(null)
const maintMeta = ref({ types: [], channels: [] })
const ledger = ref({})
const maintForm = reactive({
  type: 'cleaning', title: '', performed_at: '', cost: 0,
  channel: 'wechat', vendor: '', note: ''
})

function today() {
  return new Date().toISOString().slice(0, 10)
}

async function loadMaintMeta() {
  try {
    const res = await http.get('/maintenances/meta')
    maintMeta.value = res.data
  } catch {
    // 元信息拉取失败不阻塞抽屉，表单用默认值仍可提交
  }
}

async function openMaintenance(row) {
  maintTarget.value = row
  Object.assign(maintForm, {
    type: 'cleaning', title: '', performed_at: today(), cost: 0,
    channel: 'wechat', vendor: '', note: ''
  })
  ledger.value = {}
  maintVisible.value = true
  await loadLedger()
}

async function loadLedger() {
  if (!maintTarget.value) return
  maintLoading.value = true
  try {
    const res = await http.get(`/maintenances/ledger/${maintTarget.value.id}`)
    ledger.value = res.data
  } finally {
    maintLoading.value = false
  }
}

async function submitMaintenance() {
  if (!maintForm.title.trim()) {
    ElMessage.warning('请填写本次维护做了什么')
    return
  }
  maintSaving.value = true
  try {
    const res = await http.post('/maintenances', {
      item_id: maintTarget.value.id,
      type: maintForm.type,
      title: maintForm.title,
      performed_at: maintForm.performed_at || today(),
      cost: maintForm.cost || 0,
      channel: maintForm.channel,
      vendor: maintForm.vendor,
      note: maintForm.note
    })
    const warnings = res.data?.warnings || []
    if (warnings.length) {
      ElMessage.warning(warnings[0])
    } else {
      ElMessage.success(res.data?.cost > 0 ? `已记录，并生成开支 ¥${res.data.cost}` : '已记录')
    }
    Object.assign(maintForm, { title: '', cost: 0, vendor: '', note: '' })
    await loadLedger()
    load() // 上次维护日期变了，列表上的家庭属性标签要跟着刷新
  } finally {
    maintSaving.value = false
  }
}

async function removeMaintenance(rec) {
  await ElMessageBox.confirm(
    `删除这条维护记录「${rec.title}」？已生成的 ¥${rec.cost || 0} 开支会保留在开支明细里。`,
    '删除维护记录',
    { type: 'warning' }
  )
  await http.delete(`/maintenances/${rec.id}`)
  ElMessage.success('已删除')
  await loadLedger()
}

function openBom() {
  bomFile.value = null
  bomResult.value = null
  bomDialogVisible.value = true
}

function closeBom() {
  bomDialogVisible.value = false
}

function handleBomFileChange(file) {
  bomFile.value = file.raw
  bomResult.value = null
}

function handleBomFileRemove() {
  bomFile.value = null
  bomResult.value = null
}

async function parseBom() {
  if (!bomFile.value) {
    ElMessage.warning('请先选择 CSV 文件')
    return
  }
  const formData = new FormData()
  formData.append('file', bomFile.value)
  bomLoading.value = true
  try {
    const res = await http.post('/bom/import', formData)
    bomResult.value = res.data
  } finally {
    bomLoading.value = false
  }
}

async function applyBom() {
  if (!bomFile.value) return
  const formData = new FormData()
  formData.append('file', bomFile.value)
  bomApplying.value = true
  try {
    const res = await http.post('/bom/apply', formData)
    ElMessage.success(`已创建 ${res.data.created} 条缺失物料`)
    closeBom()
    load()
  } finally {
    bomApplying.value = false
  }
}

onMounted(() => {
  loadMeta()
  loadMaintMeta()
  load()
})
</script>

<style scoped>
.pager {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.bom-summary {
  display: flex;
  gap: 8px;
  margin: 16px 0;
}

.text-danger {
  color: #f56c6c;
  font-weight: 600;
}

.home-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.muted {
  color: #c0c4cc;
}

/* --- 批量改类型 --- */
.batch-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding: 8px 12px;
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 6px;
  background: var(--el-color-primary-light-9);
  font-size: 13px;
}

.batch-hint {
  font-size: 12px;
}

.kind-tag {
  cursor: pointer;
}

.field-hint {
  color: #a8abb2;
  font-size: 12px;
  line-height: 1.5;
}

/* --- 维护抽屉 --- */
.ledger-cards {
  margin-bottom: 12px;
}

.ledger-card {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 10px 12px;
  text-align: center;
}

.ledger-card .lv {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.ledger-card .ll {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
}

.ledger-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.maint-form {
  margin-bottom: 4px;
}

.maint-submit {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.maint-item .maint-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.maint-item .maint-title {
  font-weight: 500;
  flex: 1;
}

.maint-item .amount {
  color: #f56c6c;
  font-variant-numeric: tabular-nums;
}

.maint-item .maint-sub {
  margin-top: 4px;
  display: flex;
  gap: 10px;
  font-size: 12px;
  color: #909399;
}

:deep(.el-form-item__content) {
  gap: 8px;
}
</style>
