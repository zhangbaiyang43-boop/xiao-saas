<template>
  <div class="page-wrap">
    <!-- 顶部栏 -->
    <div class="page-header">
      <div>
        <span class="page-title">菜单管理</span>
      </div>
      <div style="display:flex;gap:8px">
        <a-button size="small" @click="openLibraryImport">菜品库导入</a-button>
        <a-button size="small" @click="showAiImport = true">AI识别导入</a-button>
        <a-button type="primary" size="small" @click="openAdd">
          <template #icon><PlusOutlined /></template>
          加菜品
        </a-button>
      </div>
    </div>

    <div v-if="isOnboarding" class="onboarding-banner">
      <span>新手引导 · 添加你的第一道菜</span>
      <button type="button" class="onboarding-back-link" @click="router.push('/activation')">返回开店引导</button>
    </div>

    <div class="summary-bar animate-in">
      <div class="summary-item">
        <span class="summary-num">{{ allDishes.length }}</span>
        <span class="summary-label">全部商品</span>
      </div>
      <div class="summary-item">
        <span class="summary-num">{{ availableCount }}</span>
        <span class="summary-label">前台可售</span>
      </div>
      <div class="summary-item">
        <span class="summary-num" :style="soldOutCount > 0 ? { color: '#ef4444' } : {}">{{ soldOutCount }}</span>
        <span class="summary-label">已售罄</span>
      </div>
    </div>
    <div v-if="soldOutCount > 0" style="padding:0 16px 12px">
      <a-button block @click="restoreAll" style="border-radius:10px;font-weight:600;color:#07C160;border-color:#07C160">
        一键恢复全部供应（{{ soldOutCount }} 个）
      </a-button>
    </div>

    <!-- 分类筛选 -->
    <div v-if="categories.length > 1" class="cat-bar animate-in" style="animation-delay:.04s">
      <span class="cat-tag" :class="{ 'cat-tag--active': activeCategory === '' }" @click="activeCategory = ''">全部</span>
      <span
        v-for="cat in categories" :key="cat"
        class="cat-tag" :class="{ 'cat-tag--active': activeCategory === cat }"
        @click="activeCategory = activeCategory === cat ? '' : cat"
      >{{ cat }}</span>
      <span class="cat-tag cat-sort-btn" @click="openCatSort" title="调整分类顺序">⇅ 排序</span>
    </div>

    <!-- 已有菜品仍在展示，仅提示本次同步失败；不清空已确认正确的旧数据 -->
    <div v-if="loadError && allDishes.length > 0" class="section-block" style="padding-top:8px">
      <a-alert type="warning" show-icon message="菜品同步失败，当前显示的是上次数据" style="border-radius:10px">
        <template #action>
          <a-button size="small" :loading="loadingMenu" @click="loadMenu">重试</a-button>
        </template>
      </a-alert>
    </div>

    <!-- 首次加载失败：没有旧数据可退回，必须独立错误态，不能落入空菜单 -->
    <div v-if="loadError && allDishes.length === 0" class="section-block" style="padding-top:8px">
      <a-alert type="error" show-icon message="菜品加载失败，请检查网络后重试" style="border-radius:10px">
        <template #action>
          <a-button size="small" :loading="loadingMenu" @click="loadMenu">重试</a-button>
        </template>
      </a-alert>
    </div>

    <!-- 骨架屏 -->
    <div v-else-if="loadingMenu && allDishes.length === 0" class="section-block">
      <a-skeleton active :paragraph="{ rows: 3 }" style="background:var(--bg-card);border-radius:12px;padding:16px;margin-bottom:12px" />
      <a-skeleton active :paragraph="{ rows: 3 }" style="background:var(--bg-card);border-radius:12px;padding:16px" />
    </div>

    <!-- 空状态：只有请求成功且确认没有菜品才展示 -->
    <div v-else-if="allDishes.length === 0" style="padding:60px 0">
      <a-empty description="还没有菜品，点右上角「加菜品」开始上架——上架的菜会出现在顾客点餐页，下架/售罄后顾客点不到">
        <a-button type="primary" @click="openAdd" style="margin-top:12px">添加第一道菜</a-button>
      </a-empty>
    </div>

    <!-- 菜品列表 -->
    <template v-else>
      <div v-for="cat in filteredCategories" :key="cat" style="padding:8px 16px 0">
        <div class="cat-header">
          <span style="font-weight:700;color:var(--text-1)">{{ cat }}</span>
          <a-tag color="default" size="small">{{ dishesByCategory(cat).length }}</a-tag>
          <a-button type="link" size="small" @click="toggleCategory(cat)" style="margin-left:auto;padding:0;color:var(--text-2)">
            {{ allAvailable(cat) ? '全部下架' : '全部上架' }}
          </a-button>
        </div>
        <a-card :bordered="false" :body-style="{ padding: 0 }">
          <div v-for="(dish, idx) in dishesByCategory(cat)" :key="dish.id" class="dish-row"
            :style="[idx > 0 ? 'border-top:1px solid var(--border)' : '', !dish.available ? 'background:var(--bg-page);opacity:.75' : '']">
            <div class="dish-emoji-box" :style="!dish.available ? 'filter:grayscale(1)' : ''" style="position:relative">
              <img v-if="dish.image" :src="dish.image" style="width:100%;height:100%;object-fit:cover;border-radius:8px" />
              <span v-else>{{ dish.emoji || '🍽️' }}</span>
              <div v-if="!dish.image && dish.available" class="no-img-badge">建议上传图片</div>
            </div>
            <div style="flex:1;min-width:0">
              <div style="display:flex;align-items:center;gap:6px;margin-bottom:2px">
                <span style="font-size:14px;font-weight:600"
                  :style="!dish.available ? { color:'var(--text-3)', textDecoration:'line-through' } : {}">{{ dish.name }}</span>
                <a-tag v-if="!dish.available" color="default" size="small">已下架</a-tag>
                <a-tag v-else-if="dish.stock !== null && dish.stock !== undefined && dish.stock <= 0" color="red" size="small">售罄</a-tag>
                <a-tag v-if="dish.spec_groups && dish.spec_groups.length" color="purple" size="small">有格</a-tag>
              </div>
              <div class="dish-meta">
                <span class="dish-cat-text">{{ dish.category || '默认' }}</span>
                <span v-if="Number(dish.sort_order || 0) > 0" class="sort-text">· 排序 {{ dish.sort_order }}</span>
                <span v-if="dish.stock !== null && dish.stock !== undefined && dish.stock > 0" style="font-size:11px;color:#d97706;font-weight:600">· 库存 {{ dish.stock }}</span>
              </div>
              <div class="dish-desc" :class="{ 'dish-desc--empty': !displayDesc(dish, true) }">{{ displayDesc(dish) }}</div>
              <div style="display:flex;align-items:baseline;gap:6px;margin-top:4px">
                <span style="font-size:16px;font-weight:900" :style="{ color: dish.available ? 'var(--text-1)' : 'var(--text-3)' }">¥{{ dish.price }}</span>
                <span v-if="dish.member_price" style="font-size:12px;color:var(--brand);font-weight:600">会员¥{{ dish.member_price }}</span>
              </div>
            </div>
            <div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px;flex-shrink:0">
              <!-- 售罄/恢复 -->
              <button
                class="sold-out-btn"
                :class="(dish.stock !== null && dish.stock !== undefined && dish.stock <= 0) ? 'sold-out-btn--restore' : 'sold-out-btn--on'"
                @click="toggleSoldOut(dish)"
              >{{ (dish.stock !== null && dish.stock !== undefined && dish.stock <= 0) ? '恢复供应' : '售罄' }}</button>
              <!-- 编辑 / 复制是高频操作，留在外面；删除不可逆，挪进"更多"菜单，
                   避免跟售罄/编辑挤在一起，忙的时候手指快容易碰到。 -->
              <div style="display:flex;gap:2px">
                <a-tooltip title="编辑">
                  <a-button type="text" size="small" aria-label="编辑" @click="openEdit(dish)" style="color:#2563eb;padding:0 6px">
                    <EditOutlined />
                  </a-button>
                </a-tooltip>
                <a-tooltip title="复制菜品">
                  <a-button type="text" size="small" aria-label="复制菜品" @click="copyDish(dish)" style="color:var(--text-2);padding:0 6px">
                    <CopyOutlined />
                  </a-button>
                </a-tooltip>
                <a-dropdown :trigger="['click']">
                  <a-button type="text" size="small" aria-label="更多" style="color:var(--text-3);padding:0 6px">
                    <EllipsisOutlined />
                  </a-button>
                  <template #overlay>
                    <a-menu>
                      <a-menu-item danger @click="confirmDeleteDish(dish)">删除菜品</a-menu-item>
                    </a-menu>
                  </template>
                </a-dropdown>
              </div>
            </div>
          </div>
        </a-card>
      </div>
    </template>

    <div style="height:16px" />

    <!-- 分类排序 Drawer -->
    <a-drawer
      v-model:open="showCatSort"
      title="调整分类顺序"
      placement="bottom"
      height="70vh"
      :body-style="{ overflowY: 'auto', paddingBottom: '80px' }"
    >
      <div style="color:var(--text-2);font-size:13px;margin-bottom:16px">拖动排序或用上下箭头调整，顾客端分类将按此顺序显示。</div>
      <div v-for="(cat, idx) in editingOrder" :key="cat" class="cat-sort-row">
        <span class="cat-sort-name">{{ cat }}</span>
        <div class="cat-sort-btns">
          <a-button size="small" :disabled="idx === 0" aria-label="上移" @click="moveCat(idx, -1)">↑</a-button>
          <a-button size="small" :disabled="idx === editingOrder.length - 1" aria-label="下移" @click="moveCat(idx, 1)">↓</a-button>
        </div>
      </div>
      <div style="position:fixed;bottom:0;left:0;right:0;padding:16px;background:var(--bg-card);box-shadow:0 -2px 8px rgba(0,0,0,.08)">
        <a-button type="primary" block :loading="savingCatOrder" @click="saveCategoryOrder">保存顺序</a-button>
      </div>
    </a-drawer>

    <!-- 添加/编辑 Drawer -->
    <a-drawer
      v-model:open="showForm"
      :title="form.id ? '编辑菜品' : '添加菜品'"
      placement="bottom"
      height="90vh"
      :close-on-mask-click="false"
      :body-style="{ overflowY: 'auto', paddingBottom: '80px' }"
      @close="onDrawerClose"
    >
      <a-form ref="formRef" :model="form" layout="vertical" @finish="saveDish" @change="formDirty = true">
        <div class="preview-block">
          <div class="preview-title">前台展示预览</div>
          <div class="mini-preview-card">
            <div class="mini-preview-img">
            <img v-if="form.image" :src="form.image" style="width:100%;height:100%;object-fit:cover;border-radius:8px" />
            <span v-else>{{ form.emoji || '🍽️' }}</span>
          </div>
            <div class="mini-preview-body">
              <div class="mini-preview-name">{{ form.name || '商品名称' }}</div>
              <div class="mini-preview-tags">
                <span>{{ form.category || '热销推荐' }}</span>
                <span>{{ form.available === false ? '下架' : '可售' }}</span>
              </div>
              <div class="mini-preview-desc">{{ form.desc || '填写一句卖点，顾客更容易下单' }}</div>
              <div class="mini-preview-price">¥{{ form.price || '0' }}</div>
            </div>
          </div>
        </div>
        <a-row :gutter="12">
          <a-col :span="6">
            <a-form-item label="图片/图标">
              <div style="display:flex;flex-direction:column;gap:6px;align-items:center">
                <div class="dish-upload-box" @click="triggerImageUpload" style="position:relative">
                  <img v-if="form.image" :src="form.image" class="dish-upload-preview" />
                  <div v-else class="dish-upload-placeholder">
                    <span style="font-size:28px">{{ form.emoji || '🍽️' }}</span>
                    <span style="font-size:11px;color:var(--text-3);margin-top:4px">上传图片</span>
                  </div>
                  <div v-if="imageUploading" class="dish-upload-loading">上传中…</div>
                  <div v-if="form.image" class="img-delete-badge" role="button" aria-label="移除图片" @click.stop="form.image = ''">×</div>
                </div>
                <a-button size="small" type="dashed" block @click="showEmojiPicker = !showEmojiPicker" style="font-size:12px;padding:0 4px">
                  {{ form.emoji || '🍽️' }} 换图标
                </a-button>
              </div>
              <input ref="imageInputRef" type="file" accept="image/*" style="display:none" @change="onImageSelected" />
              <!-- emoji 选择器 -->
              <div v-if="showEmojiPicker" class="emoji-picker-grid">
                <span v-for="e in foodEmojis" :key="e" class="emoji-option"
                  :class="{ 'emoji-option--active': form.emoji === e }"
                  @click="form.emoji = e; showEmojiPicker = false; formDirty = true">{{ e }}</span>
              </div>
            </a-form-item>
          </a-col>
          <a-col :span="18">
            <a-form-item label="菜品名称" name="name" :rules="[{ required: true, message: '请输入菜品名称' }]">
              <a-input v-model:value="form.name" placeholder="例如：炸鸡排" />
            </a-form-item>
          </a-col>
        </a-row>
        <!-- 分享到菜品库：这是锦上添花的次要动作，不该跟"菜品名称"这种核心字段同一
             视觉权重。改成图片上传后自动出现的一条轻量提示条（虚线边框+浅底色），
             一眼能看出这是"顺手勾选"而不是必填项。 -->
        <div v-if="form.image" class="library-share-strip">
          <label class="library-share-toggle">
            <a-checkbox v-model:checked="form.shareToLibrary" />
            <span>分享这张图给其他商户复用（只分享菜名和图片）</span>
          </label>
          <div v-if="form.shareToLibrary" class="library-share-options">
            <a-select v-model:value="form.libraryCuisineType" size="small" style="width:130px">
              <a-select-option value="sichuan">川菜</a-select-option>
              <a-select-option value="bbq">烧烤</a-select-option>
              <a-select-option value="universal">标准品/通用</a-select-option>
            </a-select>
            <a-radio-group v-model:value="form.libraryKind" size="small">
              <a-radio-button value="dish">现做菜品</a-radio-button>
              <a-radio-button value="standard">标准品（图片完全一致）</a-radio-button>
            </a-radio-group>
          </div>
        </div>
        <a-form-item label="卖点简介">
          <div style="display:flex;gap:8px;align-items:flex-start">
            <a-textarea v-model:value="form.desc" placeholder="例如：现做鲜奶茶，口感顺滑，推荐少冰三分糖" :rows="2" style="flex:1" />
            <a-button size="small" :loading="aiDescLoading" @click="doGenAiDesc" style="margin-top:2px;white-space:nowrap;flex-shrink:0">
              ✨ AI写卖点
            </a-button>
          </div>
        </a-form-item>
        <a-form-item label="菜品标签">
          <div style="margin-bottom:8px;display:flex;gap:8px;flex-wrap:wrap">
            <span
              v-for="preset in tagPresets"
              :key="preset"
              class="tag-preset-chip"
              :class="{ 'tag-preset-chip--on': selectedTags.includes(preset) }"
              @click="toggleTag(preset)"
            >{{ preset }}</span>
          </div>
          <div style="display:flex;gap:6px;align-items:center">
            <a-input
              v-model:value="customTagInput"
              size="small"
              placeholder="自定义标签，如：月销500份"
              style="flex:1"
              @keydown.enter.prevent="addCustomTag"
            />
            <a-button size="small" @click="addCustomTag">添加</a-button>
          </div>
          <div v-if="selectedTags.length" style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">
            <a-tag
              v-for="tag in selectedTags"
              :key="tag"
              closable
              color="green"
              @close="removeTag(tag)"
            >{{ tag }}</a-tag>
          </div>
          <div style="font-size:12px;color:var(--text-3);margin-top:4px">最多选3个，显示在点餐页菜品名称下方</div>
        </a-form-item>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="价格（元）" name="price" :rules="[{ required: true, message: '请输入价格' }]">
              <a-input-number v-model:value="form.price" placeholder="15" :min="0" style="width:100%" prefix="¥" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="分类">
              <a-select v-model:value="form.category" style="width:100%" @change="formDirty = true">
                <a-select-option v-for="cat in categoryOptions" :key="cat" :value="cat">{{ cat }}</a-select-option>
              </a-select>
              <!-- 新增分类内联区 -->
              <div v-if="showAddCategory" style="display:flex;gap:6px;margin-top:6px">
                <a-input v-model:value="newCategoryInput" size="small" placeholder="新分类名" @keydown.enter="addNewCategory" @keydown.stop />
                <a-button size="small" type="primary" @click="addNewCategory">确定</a-button>
                <a-button size="small" @click="showAddCategory = false; newCategoryInput = ''">取消</a-button>
              </div>
              <a-button v-else type="link" size="small" style="padding:0;margin-top:2px;font-size:12px" @click="showAddCategory = true">＋ 新增分类</a-button>
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="是否上架" style="margin-bottom:12px">
          <a-switch v-model:checked="form.available" checked-children="上架" un-checked-children="下架" />
        </a-form-item>

        <!-- 更多设置：会员价/划线价/排序/库存/规格都是"配一次很少再动"的字段，改价格/
             上下架这种高频编辑场景根本用不上，默认折叠减少认知负担；如果这道菜本来就
             填过这些字段，打开编辑时自动展开，不会让人找不到入口。 -->
        <div class="more-settings-toggle" @click="showMoreSettings = !showMoreSettings">
          <span class="more-settings-title">更多设置</span>
          <span class="more-settings-hint">会员价 · 划线价 · 排序 · 库存 · 规格</span>
          <span class="more-settings-arrow" :class="{ 'more-settings-arrow--open': showMoreSettings }">⌄</span>
        </div>
        <template v-if="showMoreSettings">
          <a-row :gutter="12">
            <a-col :span="12">
              <a-form-item label="前台排序">
                <a-input-number v-model:value="form.sort_order" :min="0" style="width:100%" placeholder="数字越小越靠前" />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="今日已售（可选）">
                <a-tooltip title="显示在点餐页价格旁边，增加顾客信任感，留空不显示" placement="top">
                  <a-input-number v-model:value="form.sales_count" :min="0" style="width:100%" placeholder="留空不显示" suffix="份" />
                </a-tooltip>
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="12">
            <a-col :span="12">
              <a-form-item label="会员专属价（可选）">
                <a-tooltip title="持有会员卡的顾客享受此价格，留空则不设会员价" placement="top">
                  <a-input-number v-model:value="form.member_price" placeholder="留空不设" :min="0" style="width:100%" prefix="¥" />
                </a-tooltip>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="划线价（可选）">
                <a-tooltip title="显示为删除线价格，让顾客感知实惠。如原价¥18，现价¥14.9，显示「省¥3」" placement="top">
                  <a-input-number v-model:value="form.original_price" placeholder="留空不显示" :min="0" style="width:100%" prefix="¥" @change="formDirty = true" />
                </a-tooltip>
                <div v-if="form.original_price && form.price && Number(form.original_price) > Number(form.price)" style="font-size:12px;color:#07C160;margin-top:4px">
                  顾客看到：省 ¥{{ (Number(form.original_price) - Number(form.price)).toFixed(1) }}
                </div>
              </a-form-item>
            </a-col>
          </a-row>

          <!-- 库存管理 -->
          <a-form-item label="每日库存">
            <a-radio-group v-model:value="form.stockMode" style="margin-bottom:8px" @change="formDirty = true">
              <a-radio value="unlimited">不限量</a-radio>
              <a-radio value="count">限量</a-radio>
              <a-radio value="soldout">直接售罄</a-radio>
            </a-radio-group>
            <a-input-number
              v-if="form.stockMode === 'count'"
              v-model:value="form.stock"
              :min="1"
              :max="9999"
              placeholder="今日可售份数"
              style="width:100%"
              suffix="份"
              @change="formDirty = true"
            />
            <div style="font-size:11px;color:var(--text-3);margin-top:4px">
              <span v-if="form.stockMode === 'unlimited'">顾客不限量点单</span>
              <span v-else-if="form.stockMode === 'count'">卖完自动显示售罄，库存每天需手动重置</span>
              <span v-else>立即在菜单显示售罄，顾客无法点单</span>
            </div>
          </a-form-item>

          <!-- 格配置 -->
          <a-form-item label="格选项">
            <div style="margin-bottom:8px;display:flex;gap:8px;flex-wrap:wrap">
              <a-button v-for="preset in specPresets" :key="preset.name" size="small"
                :type="form.spec_groups.some(g => g.name === preset.name) ? 'primary' : 'default'"
                @click="toggleSpecPreset(preset)">
                {{ preset.name }}
              </a-button>
              <a-button size="small" @click="addCustomSpec">＋ 自定义</a-button>
            </div>
            <div v-for="(group, gi) in form.spec_groups" :key="gi" class="spec-group">
              <div class="spec-group-head">
                <a-input v-model:value="group.name" size="small" style="width:90px;font-weight:600" />
                <a-select v-model:value="group.type" size="small" style="width:76px">
                  <a-select-option value="single">单选</a-select-option>
                  <a-select-option value="multi">多选</a-select-option>
                </a-select>
                <a-checkbox v-model:checked="group.required">必选</a-checkbox>
                <a-button type="text" danger size="small" @click="form.spec_groups.splice(gi, 1)" style="margin-left:auto">删除</a-button>
              </div>
              <div class="spec-options">
                <div v-for="(opt, oi) in group.options" :key="oi" class="spec-opt-row">
                  <a-input v-model:value="opt.name" size="small" placeholder="选项名" style="flex:1" />
                  <a-input-number v-model:value="opt.price_delta" size="small" placeholder="0" :min="0" prefix="+" style="width:80px" />
                  <a-button type="text" size="small" danger @click="group.options.splice(oi, 1)">×</a-button>
                </div>
                <a-button size="small" type="dashed" block style="margin-top:6px" @click="group.options.push({ name: '', price_delta: 0 })">添加选项</a-button>
              </div>
            </div>
            <div v-if="!form.spec_groups.length" style="font-size:12px;color:var(--text-3)">点击上方预设快速添加辣度、份量、忌口等格；饮品类可选温度、甜度</div>
          </a-form-item>
        </template>

        <!-- 底部占位，避免被固定按钮遮住 -->
        <div style="height:72px" />
      </a-form>
      <!-- 固定底部保存按钮 -->
      <div class="drawer-footer">
        <a-button type="primary" size="large" block :loading="saving" @click="submitForm">
          {{ form.id ? '保存修改' : '添加到菜单' }}
        </a-button>
      </div>
    </a-drawer>

    <!-- AI 识别导入弹窗 -->
    <a-drawer v-model:open="showAiImport" title="AI 识别菜单" placement="bottom" height="90%">
      <div v-if="aiStep === 'input'">
        <div style="font-size:13px;color:var(--text-2);margin-bottom:12px;line-height:1.7">
          把菜单文字粘贴进来，AI 自动识别菜品名称、价格和分类。<br>
          支持各种格式，例如：<br>
          <span style="color:var(--text-3)">红烧肉 28元  清炒时蔬 12  番茄蛋汤/8元</span>
        </div>
        <a-textarea
          v-model:value="aiInputText"
          placeholder="把菜单文字粘贴到这里，或者直接手打..."
          :rows="10"
          :maxlength="5000"
          show-count
          style="margin-bottom:12px"
        />
        <a-button type="primary" block size="large" :loading="aiParsing" :disabled="!aiInputText.trim()" @click="doAiParse">
          {{ aiParsing ? 'AI 识别中…' : '开始识别' }}
        </a-button>
      </div>

      <div v-else-if="aiStep === 'preview'">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
          <span style="font-size:14px;font-weight:600">识别到 {{ aiParsedItems.length }} 个菜品，确认后导入</span>
          <a-button size="small" @click="aiStep = 'input'">重新识别</a-button>
        </div>
        <div style="max-height:50vh;overflow-y:auto;margin-bottom:12px">
          <div v-for="(item, idx) in aiParsedItems" :key="idx"
            style="display:flex;align-items:center;gap:8px;padding:10px 0;border-bottom:1px solid var(--border)">
            <div style="flex:1;min-width:0">
              <a-input v-model:value="item.name" size="small" style="font-weight:600;margin-bottom:4px" />
              <div style="display:flex;gap:6px">
                <a-input-number v-model:value="item.price" size="small" prefix="¥" :min="0" style="width:90px" />
                <a-input v-model:value="item.category" size="small" placeholder="分类" style="flex:1" />
              </div>
            </div>
            <a-button size="small" danger type="text" @click="aiParsedItems.splice(idx, 1)">删除</a-button>
          </div>
        </div>
        <a-button type="primary" block size="large" :loading="aiImporting" @click="doAiImport">
          导入全部 {{ aiParsedItems.length }} 个菜品
        </a-button>
      </div>
    </a-drawer>

    <!-- 菜品库导入：其他商户分享出来的菜品（图片是他们自己实拍的），按菜系/关键词
         搜出来，勾选后一键导入，标准品直接复用图片，现做菜品会提示"建议后续换成实拍"。 -->
    <a-drawer v-model:open="showLibraryImport" title="从菜品库导入" placement="bottom" height="90%" @close="resetLibraryImport">
      <div v-if="libraryStep === 'browse'">
        <div style="display:flex;gap:8px;margin-bottom:10px">
          <a-input v-model:value="libraryKeyword" placeholder="搜菜名，如：鱼香肉丝" allow-clear @keydown.enter="doLibrarySearch" />
          <a-button @click="doLibrarySearch">搜索</a-button>
        </div>
        <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">
          <span
            v-for="f in libraryCuisineFilters"
            :key="f.val"
            class="cat-tag"
            :class="{ 'cat-tag--active': libraryCuisineFilter === f.val }"
            @click="libraryCuisineFilter = f.val; doLibrarySearch()"
          >{{ f.label }}</span>
        </div>
        <div v-if="librarySearching" style="padding:32px 0;text-align:center;color:var(--text-3)">搜索中…</div>
        <div v-else-if="libraryError" style="padding:32px 0;text-align:center;color:var(--text-3);font-size:13px">
          搜索失败，请检查网络后重试
          <div style="margin-top:10px"><a-button size="small" @click="doLibrarySearch">重试</a-button></div>
        </div>
        <div v-else-if="libraryItems.length === 0" style="padding:32px 0;text-align:center;color:var(--text-3);font-size:13px">
          还没有商户分享过这道菜，先自己上传吧——下次别的店就能直接用你这张图了
        </div>
        <div v-else style="max-height:56vh;overflow-y:auto">
          <div v-for="item in libraryItems" :key="item.id"
            style="display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--border)">
            <div style="width:48px;height:48px;border-radius:8px;overflow:hidden;flex-shrink:0;background:var(--bg-page)">
              <img v-if="item.image" :src="item.image" style="width:100%;height:100%;object-fit:cover" />
            </div>
            <div style="flex:1;min-width:0">
              <div style="font-size:14px;font-weight:600;color:var(--text-1)">{{ item.name }}</div>
              <div style="display:flex;align-items:center;gap:6px;margin-top:2px">
                <a-tag size="small" :color="item.kind === 'standard' ? 'blue' : 'orange'">{{ item.kind === 'standard' ? '标准品·图片通用' : '参考图·建议后续换实拍' }}</a-tag>
                <span v-if="item.reference_price" style="font-size:12px;color:var(--text-3)">参考¥{{ item.reference_price }}</span>
              </div>
            </div>
            <a-checkbox :checked="librarySelected.has(item.id)" @change="toggleLibrarySelect(item)" />
          </div>
        </div>
        <div style="position:sticky;bottom:0;background:var(--bg-card);padding-top:10px">
          <a-button type="primary" block size="large" :disabled="librarySelected.size === 0" @click="goToLibraryPreview">
            下一步（已选 {{ librarySelected.size }} 个）
          </a-button>
        </div>
      </div>

      <div v-else-if="libraryStep === 'preview'">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
          <span style="font-size:14px;font-weight:600">确认价格和分类后导入</span>
          <a-button size="small" @click="libraryStep = 'browse'">返回修改</a-button>
        </div>
        <div style="max-height:56vh;overflow-y:auto;margin-bottom:12px">
          <div v-for="item in libraryPreviewItems" :key="item.id"
            style="display:flex;align-items:center;gap:8px;padding:10px 0;border-bottom:1px solid var(--border)">
            <div style="width:40px;height:40px;border-radius:8px;overflow:hidden;flex-shrink:0;background:var(--bg-page)">
              <img v-if="item.image" :src="item.image" style="width:100%;height:100%;object-fit:cover" />
            </div>
            <div style="flex:1;min-width:0">
              <div style="font-size:14px;font-weight:600;margin-bottom:4px">{{ item.name }}</div>
              <div style="display:flex;gap:6px">
                <a-input-number v-model:value="item.price" size="small" prefix="¥" :min="0" style="width:90px" />
                <a-input v-model:value="item.category" size="small" placeholder="分类" style="flex:1" />
              </div>
            </div>
          </div>
        </div>
        <a-button type="primary" block size="large" :loading="libraryImporting" @click="doLibraryImport">
          导入全部 {{ libraryPreviewItems.length }} 个菜品
        </a-button>
      </div>
    </a-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { PlusOutlined, EditOutlined, CopyOutlined, EllipsisOutlined } from '@ant-design/icons-vue'
import { getMenuItems, createMenuItem, updateMenuItem, deleteMenuItem, uploadDishImage, getTenantSettings, updateTenantSettings, updateMenuItemStock, parseMenuText, importMenuBatch, generateDishDesc, searchDishLibrary, contributeDishToLibrary, importDishLibraryBatch } from '../api'
import { markPageContentReady } from '../utils/adminPerformance'

const route = useRoute()
const router = useRouter()
// Onboarding continuation (Activation Home Step 1) is a thin, opt-in overlay
// on this same page -- only active when arriving via ?onboarding=1. Normal
// /menu navigation must behave exactly as before (see maybeCompleteOnboardingStep1
// below, which is a no-op unless isOnboarding is true).
const isOnboarding = computed(() => route.query.onboarding === '1')

const loadingMenu = ref(false)
const loadError = ref(false)
const saving = ref(false)
const showForm = ref(false)
const allDishes = ref([])
const activeCategory = ref('')
const categoryOrder = ref([])   // 商家设置的分类顺序
const showCatSort = ref(false)  // 分类排序抽屉
const savingCatOrder = ref(false)
const showEmojiPicker = ref(false)
const showAddCategory = ref(false)
const newCategoryInput = ref('')

const foodEmojis = ['🍽️','🍜','🍲','🥘','🍛','🍣','🍱','🍤','🥗','🥩','🍗','🥦','🍔','🌮','🥪','🥙','🍕','🌯','🍝','🥟','🍦','🧁','🎂','🍰','🍮','🧋','☕','🍵','🥤','🍺','🍷','🧃']

const specPresets = [
  { name: '辣度', type: 'single', required: false, options: [{ name: '不辣', price_delta: 0 }, { name: '微辣', price_delta: 0 }, { name: '中辣', price_delta: 0 }, { name: '重辣', price_delta: 0 }] },
  { name: '份量', type: 'single', required: false, options: [{ name: '小份', price_delta: 0 }, { name: '大份', price_delta: 3 }] },
  { name: '做法', type: 'single', required: false, options: [{ name: '清淡', price_delta: 0 }, { name: '正常', price_delta: 0 }, { name: '重口', price_delta: 0 }] },
  { name: '忌口', type: 'multi', required: false, options: [{ name: '不要葱', price_delta: 0 }, { name: '不要香菜', price_delta: 0 }, { name: '不要蒜', price_delta: 0 }] },
  // 饮品专用
  { name: '温度', type: 'single', required: true, options: [{ name: '热', price_delta: 0 }, { name: '温', price_delta: 0 }, { name: '冰', price_delta: 0 }] },
  { name: '甜度', type: 'single', required: true, options: [{ name: '正常', price_delta: 0 }, { name: '少糖', price_delta: 0 }, { name: '无糖', price_delta: 0 }] },
  { name: '杯型', type: 'single', required: true, options: [{ name: '中杯', price_delta: 0 }, { name: '大杯', price_delta: 3 }] },
]

const form = reactive({ id: null, name: '', desc: '', price: '', member_price: null, original_price: null, category: '热销推荐', emoji: '🍽️', available: true, sort_order: 0, spec_groups: [], image: '', sales_count: null, tags: '', stock: null, stockMode: 'unlimited', shareToLibrary: false, libraryCuisineType: 'sichuan', libraryKind: 'dish' })

const tagPresets = ['本店特色', '招牌必点', '热卖', '新品', '限时特惠', '月销500+', '好评如潮', '老推荐']
const selectedTags = ref([])
const customTagInput = ref('')

function toggleTag(tag) {
  const idx = selectedTags.value.indexOf(tag)
  if (idx !== -1) { selectedTags.value.splice(idx, 1); return }
  if (selectedTags.value.length >= 3) { message.warning('最多选3个标签'); return }
  selectedTags.value.push(tag)
  formDirty.value = true
}

function addCustomTag() {
  const t = customTagInput.value.trim()
  if (!t) return
  if (selectedTags.value.includes(t)) { customTagInput.value = ''; return }
  if (selectedTags.value.length >= 3) { message.warning('最多选3个标签'); return }
  selectedTags.value.push(t)
  customTagInput.value = ''
  formDirty.value = true
}

function removeTag(tag) {
  selectedTags.value = selectedTags.value.filter(t => t !== tag)
  formDirty.value = true
}
const imageInputRef = ref(null)
const imageUploading = ref(false)

function triggerImageUpload() { imageInputRef.value?.click() }

async function onImageSelected(e) {
  const file = e.target.files?.[0]
  if (!file) return
  imageUploading.value = true
  try {
    const res = await uploadDishImage(file)
    const url = res?.data?.data?.url || res?.data?.url
    if (url) { form.image = url; message.success('图片已上传，点保存按钮生效') }
    else message.error('上传失败')
  } catch { message.error('上传失败，请重试') }
  finally { imageUploading.value = false; e.target.value = '' }
}

function toggleSpecPreset(preset) {
  const idx = form.spec_groups.findIndex(g => g.name === preset.name)
  if (idx !== -1) form.spec_groups.splice(idx, 1)
  else form.spec_groups.push(JSON.parse(JSON.stringify(preset)))
}

function addCustomSpec() {
  form.spec_groups.push({ name: '自定义', type: 'single', required: false, options: [{ name: '', price_delta: 0 }] })
}

const categories = computed(() => {
  // 从菜品里收集所有真实分类
  const raw = []
  for (const d of allDishes.value) if (d.category && !raw.includes(d.category)) raw.push(d.category)
  // 按 categoryOrder 排序，未配置的分类追加到末尾
  const order = categoryOrder.value
  if (!order.length) return raw
  // 去重：category_order 里同一个分类出现两次的话（历史脏数据/排序抽屉曾经没做去重），
  // 小程序端 menu.vue 是按这个数组下标生成分类锚点 id 的，重复项会导致点分类跳错、
  // 滚动定位错乱——这里和排序抽屉的 openCatSort 都要保证吐出去的数组不带重复。
  const seen = new Set()
  const sorted = order.filter(c => raw.includes(c) && !seen.has(c) && seen.add(c))
  raw.forEach(c => { if (!sorted.includes(c)) sorted.push(c) })
  return sorted
})

// 分类下拉选项：已有分类 + 可新增
const categoryOptions = computed(() => {
  const base = categories.value.length ? categories.value : ['热销推荐']
  if (form.category && !base.includes(form.category)) return [...base, form.category]
  return base
})

function addNewCategory() {
  const v = newCategoryInput.value.trim()
  if (v) { form.category = v; newCategoryInput.value = ''; formDirty.value = true }
}

const filteredCategories = computed(() => activeCategory.value ? [activeCategory.value] : categories.value)
const availableCount = computed(() => allDishes.value.filter(d => d.available !== false).length)

// Section 6: not just createMenuItem -- any action that can bring the
// available-dish count above zero (create, edit-to-available, bulk
// category restore, restore-all) should be able to complete onboarding
// Step 1. Reuses the same availableCount this page already displays; no new
// backend call, no fabricated completion.
function maybeCompleteOnboardingStep1() {
  if (isOnboarding.value && availableCount.value > 0) router.replace('/activation')
}
const soldOutCount = computed(() => allDishes.value.filter(d => d.available === false || (d.stock !== null && d.stock !== undefined && d.stock <= 0)).length)

function dishesByCategory(cat) { return allDishes.value.filter(d => d.category === cat) }
function allAvailable(cat) { return dishesByCategory(cat).every(d => d.available !== false) }
function displayDesc(dish, raw) {
  const real = dish.desc || dish.description || ''
  return raw ? real : (real || '还没有填写卖点简介')
}

const formDirty = ref(false)
const showMoreSettings = ref(false)
function dishHasMoreSettings(d) {
  return Boolean(
    d.member_price || d.original_price || Number(d.sort_order || 0) > 0 ||
    (d.sales_count !== null && d.sales_count !== undefined) ||
    (d.stock !== null && d.stock !== undefined) ||
    (d.spec_groups && d.spec_groups.length)
  )
}

function onDrawerClose(e) {
  if (formDirty.value) {
    e?.preventDefault?.()
    Modal.confirm({
      title: '离开编辑？',
      content: '未保存的内容将会丢失',
      okText: '离开',
      cancelText: '继续编辑',
      onOk: () => { formDirty.value = false; showForm.value = false },
    })
    return false
  }
}

function openAdd() {
  Object.assign(form, { id: null, name: '', desc: '', price: '', member_price: null, original_price: null, category: categories.value[0] || '热销推荐', emoji: '🍽️', available: true, sort_order: 0, spec_groups: [], image: '', tags: '', stock: null, stockMode: 'unlimited', shareToLibrary: false, libraryCuisineType: 'sichuan', libraryKind: 'dish' })
  selectedTags.value = []
  customTagInput.value = ''
  formDirty.value = false
  showEmojiPicker.value = false
  showAddCategory.value = false
  showMoreSettings.value = false
  showForm.value = true
}

function openEdit(dish) {
  const stockMode = dish.stock === null || dish.stock === undefined ? 'unlimited' : dish.stock <= 0 ? 'soldout' : 'count'
  Object.assign(form, { ...dish, member_price: dish.member_price ?? null, spec_groups: JSON.parse(JSON.stringify(dish.spec_groups || [])), stock: dish.stock ?? null, stockMode, shareToLibrary: false, libraryCuisineType: 'sichuan', libraryKind: 'dish' })
  showMoreSettings.value = dishHasMoreSettings(dish)
  // 解析已保存的 tags
  const rawTags = dish.tags
  if (Array.isArray(rawTags)) selectedTags.value = [...rawTags].slice(0, 3)
  else if (typeof rawTags === 'string' && rawTags.trim()) selectedTags.value = rawTags.split(',').map(t => t.trim()).filter(Boolean).slice(0, 3)
  else selectedTags.value = []
  customTagInput.value = ''
  formDirty.value = false
  showEmojiPicker.value = false
  showAddCategory.value = false
  showForm.value = true
}

const formRef = ref(null)

async function submitForm() {
  try { await formRef.value?.validate() } catch { return }
  await saveDish()
}

async function saveDish() {
  if (!form.name || !form.price) { message.error('名称和价格不能为空'); return }
  saving.value = true
  try {
    const stockVal = form.stockMode === 'unlimited' ? null : form.stockMode === 'soldout' ? 0 : (Number(form.stock) || 0)
    const payload = { name: form.name, description: form.desc, price: Number(form.price), member_price: form.member_price != null ? Number(form.member_price) : null, original_price: form.original_price != null ? Number(form.original_price) : null, category: form.category || '其他', emoji: form.emoji || '🍽️', available: form.available !== false, sort_order: Number(form.sort_order || 0), spec_groups: form.spec_groups.length ? form.spec_groups : undefined, image: form.image || null, sales_count: form.sales_count != null ? Number(form.sales_count) : null, tags: selectedTags.value.length ? selectedTags.value.join(',') : null, stock: stockVal }
    if (form.id) {
      await updateMenuItem(form.id, payload)
      const idx = allDishes.value.findIndex(d => d.id === form.id)
      if (idx !== -1) allDishes.value[idx] = { ...allDishes.value[idx], ...payload, desc: payload.description }
    } else {
      const res = await createMenuItem(payload)
      const created = res?.data?.data || res?.data || { ...payload, id: Date.now() }
      allDishes.value.push({ ...created, desc: created.description || payload.description || '', sort_order: created.sort_order ?? payload.sort_order })
    }
    message.success(form.id ? '已保存' : (isOnboarding.value ? '第一道菜已添加' : '已添加'))
    if (form.shareToLibrary && form.image) {
      // 分享到菜品库是锦上添花的动作，失败了不该打断商户本来的保存流程，静默失败即可
      contributeDishToLibrary({
        name: form.name,
        category: form.category || null,
        cuisine_type: form.libraryCuisineType,
        kind: form.libraryKind,
        image: form.image,
        reference_price: Number(form.price) || null,
      }).catch(() => {})
    }
    formDirty.value = false
    showForm.value = false
    maybeCompleteOnboardingStep1()
  } catch { message.error('保存失败') }
  finally { saving.value = false }
}

async function toggleAvailable(dish, val) {
  try { await updateMenuItem(dish.id, { available: val }); dish.available = val }
  catch { dish.available = !val; message.error('更新失败') }
}

async function toggleSoldOut(dish) {
  const isSoldOut = dish.stock !== null && dish.stock !== undefined && dish.stock <= 0
  const newStock = isSoldOut ? null : 0
  try {
    await updateMenuItemStock(dish.id, newStock)
    dish.stock = newStock
    dish.sold_out = newStock !== null && newStock <= 0
    message.success(isSoldOut ? '已恢复供应' : '已标记售罄')
  } catch { message.error('操作失败') }
}

async function restoreAll() {
  const byAvailable = allDishes.value.filter(d => d.available === false)
  const byStock = allDishes.value.filter(d => d.stock !== null && d.stock !== undefined && d.stock <= 0)
  byAvailable.forEach(d => { d.available = true })
  byStock.forEach(d => { d.stock = null; d.sold_out = false })
  try {
    await Promise.all([
      ...byAvailable.map(d => updateMenuItem(d.id, { available: true })),
      ...byStock.map(d => updateMenuItemStock(d.id, null)),
    ])
    message.success(`已恢复 ${byAvailable.length + byStock.length} 个菜品供应`)
    maybeCompleteOnboardingStep1()
  } catch { message.error('操作失败'); await loadMenu() }
}

function copyDish(dish) {
  Object.assign(form, {
    ...dish,
    id: null,
    name: dish.name + '-副本',
    member_price: dish.member_price ?? null,
    spec_groups: JSON.parse(JSON.stringify(dish.spec_groups || [])),
    shareToLibrary: false,
    libraryCuisineType: 'sichuan',
    libraryKind: 'dish',
  })
  formDirty.value = true
  showEmojiPicker.value = false
  showAddCategory.value = false
  showMoreSettings.value = dishHasMoreSettings(dish)
  showForm.value = true
}

async function deleteDish(dish) {
  try { await deleteMenuItem(dish.id); allDishes.value = allDishes.value.filter(d => d.id !== dish.id); message.success('已删除') }
  catch { message.error('删除失败') }
}

function confirmDeleteDish(dish) {
  Modal.confirm({
    title: `删除「${dish.name}」？`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: () => deleteDish(dish),
  })
}

async function toggleCategory(cat) {
  const dishes = dishesByCategory(cat)
  const targetVal = !allAvailable(cat)
  dishes.forEach(d => { d.available = targetVal })
  try {
    await Promise.all(dishes.map(d => updateMenuItem(d.id, { available: targetVal })))
    maybeCompleteOnboardingStep1()
  } catch { message.error('操作失败'); await loadMenu() }
}

async function loadMenu() {
  loadingMenu.value = true
  let resultStatus = 'success'
  try {
    const res = await getMenuItems()
    if (res?.code !== 200) throw new Error(res?.msg || '菜品加载失败')
    const raw = res?.data?.data?.items || res?.data?.items || res?.data || []
    if (!Array.isArray(raw)) throw new Error('菜品数据格式异常')
    allDishes.value = raw.map(d => ({ ...d, desc: d.desc ?? d.description ?? '', sort_order: d.sort_order ?? 0 }))
    loadError.value = false
    resultStatus = allDishes.value.length ? 'success' : 'empty'
  } catch {
    // 失败不清空已确认正确的旧菜单——加载失败不等于没有菜，保留旧数据由模板的
    // loadError 横幅去标记"可能过期"，而不是让老板以为菜品真的被清空了。
    loadError.value = true
    resultStatus = 'error'
  } finally {
    loadingMenu.value = false
    markPageContentReady({
      page: 'DishManage',
      status: resultStatus,
      data_count: allDishes.value.length,
    })
  }
}

// 分类排序：加载已保存的顺序
async function loadCategoryOrder() {
  try {
    const res = await getTenantSettings()
    const order = res?.data?.business_info?.category_order || res?.data?.category_order
    if (Array.isArray(order) && order.length) categoryOrder.value = order
  } catch {}
}

// 分类排序抽屉里的临时列表（用于编辑）
const editingOrder = ref([])
function openCatSort() {
  // 合并已有顺序 + 当前实际分类（新增的会追加到末尾）；顺便把已保存顺序里可能存在的
  // 重复项去掉，不然点一次"保存"就把脏数据原样写回去了。
  const current = categories.value
  const seenSaved = new Set()
  const saved = categoryOrder.value.filter(c => current.includes(c) && !seenSaved.has(c) && seenSaved.add(c))
  current.forEach(c => { if (!saved.includes(c)) saved.push(c) })
  editingOrder.value = saved
  showCatSort.value = true
}
function moveCat(idx, dir) {
  const arr = [...editingOrder.value]
  const target = idx + dir
  if (target < 0 || target >= arr.length) return
  ;[arr[idx], arr[target]] = [arr[target], arr[idx]]
  editingOrder.value = arr
}
async function saveCategoryOrder() {
  savingCatOrder.value = true
  try {
    await updateTenantSettings({ category_order: editingOrder.value })
    categoryOrder.value = editingOrder.value
    showCatSort.value = false
    message.success('分类顺序已保存')
  } catch { message.error('保存失败') }
  finally { savingCatOrder.value = false }
}

// AI 识别导入
const showAiImport = ref(false)
const aiStep = ref('input')  // input | preview
const aiInputText = ref('')
const aiParsedItems = ref([])
const aiParsing = ref(false)
const aiImporting = ref(false)

async function doAiParse() {
  if (!aiInputText.value.trim()) return
  aiParsing.value = true
  try {
    const res = await parseMenuText(aiInputText.value)
    if (res?.code === 200 && res?.data?.length) {
      aiParsedItems.value = res.data.map(d => ({ ...d }))
      aiStep.value = 'preview'
    } else {
      message.error(res?.msg || '未识别到菜品，请检查文字格式')
    }
  } catch { message.error('识别失败，请稍后重试') }
  finally { aiParsing.value = false }
}

async function doAiImport() {
  if (!aiParsedItems.value.length) return
  aiImporting.value = true
  try {
    const res = await importMenuBatch(aiParsedItems.value)
    if (res?.code === 200) {
      message.success(`成功导入 ${res.data?.count || aiParsedItems.value.length} 个菜品`)
      showAiImport.value = false
      aiStep.value = 'input'
      aiInputText.value = ''
      aiParsedItems.value = []
      await loadMenu()
    } else {
      message.error(res?.msg || '导入失败')
    }
  } catch { message.error('导入失败，请重试') }
  finally { aiImporting.value = false }
}

// 菜品库导入：浏览/搜索其他商户分享出来的菜品，勾选后批量导入
const showLibraryImport = ref(false)
const libraryStep = ref('browse')  // browse | preview
const libraryKeyword = ref('')
const libraryCuisineFilter = ref('')
const libraryCuisineFilters = [
  { label: '全部', val: '' },
  { label: '川菜', val: 'sichuan' },
  { label: '烧烤', val: 'bbq' },
  { label: '标准品', val: 'universal' },
]
const libraryItems = ref([])
const librarySearching = ref(false)
const libraryError = ref(false)
const librarySelected = ref(new Set())
const libraryPreviewItems = ref([])
const libraryImporting = ref(false)

function openLibraryImport() {
  showLibraryImport.value = true
  libraryStep.value = 'browse'
  librarySelected.value = new Set()
  doLibrarySearch()
}

function resetLibraryImport() {
  libraryStep.value = 'browse'
  libraryKeyword.value = ''
  libraryCuisineFilter.value = ''
  libraryItems.value = []
  libraryError.value = false
  librarySelected.value = new Set()
  libraryPreviewItems.value = []
}

async function doLibrarySearch() {
  librarySearching.value = true
  try {
    const res = await searchDishLibrary({ keyword: libraryKeyword.value.trim() || undefined, cuisine_type: libraryCuisineFilter.value || undefined })
    if (res?.code !== 200) throw new Error(res?.msg || '搜索失败')
    const raw = res?.data?.data || res?.data || []
    if (!Array.isArray(raw)) throw new Error('搜索结果格式异常')
    libraryItems.value = raw
    libraryError.value = false
  } catch {
    // 搜索失败不清空上一次的正确结果——避免把"网络抖了一下"误显成"这道菜没人分享过"。
    libraryError.value = true
  }
  finally { librarySearching.value = false }
}

function toggleLibrarySelect(item) {
  const next = new Set(librarySelected.value)
  if (next.has(item.id)) next.delete(item.id)
  else next.add(item.id)
  librarySelected.value = next
}

function goToLibraryPreview() {
  libraryPreviewItems.value = libraryItems.value
    .filter(i => librarySelected.value.has(i.id))
    .map(i => ({ id: i.id, name: i.name, image: i.image, category: i.category || '默认', price: i.reference_price || 0 }))
  libraryStep.value = 'preview'
}

async function doLibraryImport() {
  if (!libraryPreviewItems.value.length) return
  libraryImporting.value = true
  try {
    const res = await importDishLibraryBatch(libraryPreviewItems.value.map(i => ({ id: i.id, price: Number(i.price) || 0, category: i.category })))
    if (res?.code === 200) {
      message.success(`成功导入 ${res.data?.count || libraryPreviewItems.value.length} 个菜品`)
      showLibraryImport.value = false
      resetLibraryImport()
      await loadMenu()
    } else {
      message.error(res?.msg || '导入失败')
    }
  } catch { message.error('导入失败，请重试') }
  finally { libraryImporting.value = false }
}

const aiDescLoading = ref(false)
async function doGenAiDesc() {
  if (!form.name?.trim()) {
    message.warning('请先填写菜品名称')
    return
  }
  aiDescLoading.value = true
  try {
    const res = await generateDishDesc({
      name: form.name.trim(),
      price: form.price || 0,
      category: form.category || '热销推荐',
    })
    if (res.data?.description) {
      form.desc = res.data.description
    }
  } catch (e) {
    message.error('AI生成失败，请稍后重试')
  } finally {
    aiDescLoading.value = false
  }
}

onMounted(() => {
  loadCategoryOrder()
  if (isOnboarding.value) {
    // Onboarding is gated on loadMenu() resolving first (need a real
    // availableCount before deciding skip-vs-auto-open); normal navigation
    // keeps the original fire-and-forget parallel load untouched below.
    loadMenu().then(() => {
      if (availableCount.value > 0) router.replace('/activation')
      else openAdd()
    })
  } else {
    loadMenu()
  }
})
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 52px 16px 12px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
}
.page-title { font-size: 18px; font-weight: 700; color: var(--text-1); }

.onboarding-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
  background: var(--brand-light);
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  font-weight: 600;
  color: var(--brand);
}
.onboarding-back-link {
  border: none;
  background: transparent;
  color: var(--text-2);
  font-size: 12px;
  font-weight: 600;
  text-decoration: underline;
  flex-shrink: 0;
}

.summary-bar {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  padding: 12px 16px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
}

.summary-item {
  padding: 10px 8px;
  border-radius: 12px;
  background: var(--brand-light);
  border: 1px solid var(--border);
}

.summary-num {
  display: block;
  color: var(--brand);
  font-size: 20px;
  line-height: 1;
  font-weight: 800;
}

.summary-label {
  display: block;
  margin-top: 6px;
  color: var(--text-2);
  font-size: 12px;
}

.cat-bar {
  background: var(--bg-card);
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  overflow-x: auto;
  white-space: nowrap;
  scrollbar-width: none;
  &::-webkit-scrollbar { display: none; }
}
.cat-sort-btn {
  border-color: var(--border) !important;
  color: var(--text-2) !important;
  background: var(--bg-page) !important;
}
.cat-sort-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  margin-bottom: 8px;
  border-radius: 10px;
  background: var(--bg-page);
  border: 1px solid var(--border);
}
.cat-sort-name { font-size: 15px; font-weight: 600; color: var(--text-1); }
.cat-sort-btns { display: flex; gap: 6px; }
.cat-tag {
  display: inline-block;
  margin-right: 8px;
  padding: 4px 14px;
  border-radius: 20px;
  font-size: 13px;
  cursor: pointer;
  border: 1px solid var(--border);
  color: var(--text-2);
  background: var(--bg-page);
  transition: transform .15s, all .15s;
  &:active { transform: scale(.95); }
}

.cat-tag--active {
  border-color: var(--brand);
  color: var(--brand);
  background: var(--brand-light);
  font-weight: 600;
}

.cat-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 0 6px;
  font-size: 14px;
}

.dish-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
}

.dish-emoji-box {
  width: 60px;
  height: 60px;
  border-radius: 12px;
  background: var(--brand-light);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  flex-shrink: 0;
  overflow: visible;
  position: relative;
}

.tag-preset-chip {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 20px;
  font-size: 12px;
  border: 1px solid #d1fae5;
  background: #f0fdf4;
  color: #065f46;
  cursor: pointer;
  user-select: none;
  transition: all .15s, transform .15s;
  &:active { transform: scale(.93); }
}

.tag-preset-chip--on {
  background: #07C160;
  color: #fff;
  border-color: #07C160;
}

.no-img-badge {
  position: absolute;
  bottom: -8px;
  left: 50%;
  transform: translateX(-50%);
  background: #f59e0b;
  color: #fff;
  font-size: 9px;
  font-weight: 600;
  padding: 1px 5px;
  border-radius: 4px;
  white-space: nowrap;
  pointer-events: none;
}

.dish-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.sort-text {
  color: var(--text-3);
  font-size: 12px;
}

/* 分类原来用彩色 a-tag 药丸展示，跟菜名同一视觉权重抢注意力；改成纯文字，
   跟排序/库存这些次要信息同一量级，价格和菜名才是这一行真正该先看到的东西。 */
.dish-cat-text {
  font-size: 12px;
  color: var(--text-3);
}

.dish-desc {
  max-width: 100%;
  font-size: 12px;
  color: var(--text-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dish-desc--empty {
  color: var(--text-3);
  font-style: italic;
}

.sold-out-btn {
  display: inline-block;
  padding: 5px 14px;
  border-radius: 20px;
  border: 1.5px solid;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
  background: none;
  transition: all .15s;
  min-width: 68px;
  text-align: center;
}
.sold-out-btn--on {
  border-color: var(--border);
  color: var(--text-3);
  &:active { background: var(--bg-page); }
}
.sold-out-btn--restore {
  border-color: #07C160;
  color: #07C160;
  background: #f0fdf4;
  &:active { background: #dcfce7; }
}

.more-settings-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 0;
  cursor: pointer;
  user-select: none;
  border-top: 1px solid var(--border);
  margin-top: 4px;
}
.more-settings-title { font-size: 13px; font-weight: 600; color: var(--text-1); }
.more-settings-hint { font-size: 11px; color: var(--text-3); flex: 1; }
.more-settings-arrow {
  color: var(--text-3);
  transition: transform .15s;
}
.more-settings-arrow--open { transform: rotate(180deg); }

.library-share-strip {
  margin-bottom: 16px;
  padding: 8px 12px;
  border-radius: 10px;
  background: var(--bg-page);
  border: 1px dashed var(--border);
}
.library-share-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-2);
  cursor: pointer;
}
.library-share-options {
  margin-top: 8px;
  padding-left: 22px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.preview-block {
  margin-bottom: 16px;
  padding: 12px;
  border-radius: 16px;
  background: var(--bg-page);
  border: 1px solid var(--border);
}

.preview-title {
  margin-bottom: 10px;
  color: var(--text-2);
  font-size: 13px;
  font-weight: 700;
}

.mini-preview-card {
  display: flex;
  gap: 12px;
  padding: 12px;
  border-radius: 14px;
  background: var(--bg-card);
}

.dish-upload-box {
  width: 80px;
  height: 80px;
  border-radius: 12px;
  border: 1.5px dashed var(--border);
  cursor: pointer;
  overflow: hidden;
  position: relative;
  background: var(--bg-page);
  display: flex;
  align-items: center;
  justify-content: center;
  &:hover { border-color: #07C160; }
}
.dish-upload-preview {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.dish-upload-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.dish-upload-loading {
  position: absolute;
  inset: 0;
  background: rgba(0,0,0,.5);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: #fff;
}

.mini-preview-img {
  width: 72px;
  height: 72px;
  border-radius: 14px;
  background: var(--bg-page);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 34px;
  flex-shrink: 0;
}

.mini-preview-body {
  flex: 1;
  min-width: 0;
}

.mini-preview-name {
  color: var(--text-1);
  font-size: 15px;
  font-weight: 800;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mini-preview-tags {
  display: flex;
  gap: 6px;
  margin-top: 6px;
}

.mini-preview-tags span {
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid #d6b57c;
  background: #fffaf0;
  color: #9a6a21;
  font-size: 11px;
}

.mini-preview-desc {
  margin-top: 6px;
  color: var(--text-3);
  font-size: 12px;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.mini-preview-price {
  margin-top: 8px;
  color: var(--brand);
  font-size: 18px;
  font-weight: 900;
}

:deep(.ant-drawer-body) {
  padding-bottom: 0;
  overflow-y: auto;
}

.drawer-footer {
  position: sticky;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 12px 16px max(env(safe-area-inset-bottom), 12px);
  background: var(--bg-card);
  border-top: 1px solid var(--border);
  z-index: 10;
}

.img-delete-badge {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: rgba(0,0,0,.55);
  color: #fff;
  font-size: 13px;
  line-height: 18px;
  text-align: center;
  cursor: pointer;
  display: none;
}
.dish-upload-box:hover .img-delete-badge { display: block; }

.emoji-picker-grid {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 4px;
  padding: 8px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  margin-top: 6px;
  box-shadow: var(--card-shadow);
}

.emoji-option {
  font-size: 22px;
  text-align: center;
  cursor: pointer;
  border-radius: 6px;
  padding: 2px;
  transition: background .12s;
  &:hover { background: #f0fdf4; }
}

.emoji-option--active {
  background: #dcfce7;
  outline: 2px solid #07C160;
}

.spec-group {
  border: 1px solid var(--border);
  border-radius: 10px;
  margin-bottom: 10px;
  overflow: hidden;
}
.spec-group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--bg-page);
  border-bottom: 1px solid var(--border);
}
.spec-options {
  padding: 10px 12px;
}
.spec-opt-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
</style>
