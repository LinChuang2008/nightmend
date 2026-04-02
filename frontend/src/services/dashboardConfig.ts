/**
 * Dashboard 配置管理服务
 * 
 * 提供 Dashboard 布局的 CRUD 操作、预设模板管理、组件配置等功能。
 * 支持用户自定义Dashboard布局，保存多个配置方案，在不同方案间切换。
 */
import api from './api';

// ==================== 类型定义 ====================

export interface ComponentConfig {
  id: string;
  name: string;
  visible: boolean;
  position: {
    row: number;
    col: number;
    span: number;
  };
  size?: {
    width?: number;
    height?: number;
  };
  settings?: Record<string, any>;
}

export interface DashboardLayout {
  id?: number;
  user_id?: number;
  name: string;
  description?: string;
  is_active: boolean;
  is_preset: boolean;
  grid_cols: number;
  config: {
    components: ComponentConfig[];
  };
  created_at?: string;
  updated_at?: string;
}

export interface DashboardComponent {
  id: string;
  name: string;
  description?: string;
  category: string;
  default_config?: Record<string, any>;
  is_enabled: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface PresetLayout {
  id: string;
  name: string;
  description: string;
  preview_image?: string;
  config: {
    components: ComponentConfig[];
  };
}

export interface DashboardConfig {
  current_layout?: DashboardLayout;
  available_components: DashboardComponent[];
  preset_layouts: PresetLayout[];
  user_layouts: DashboardLayout[];
}

export interface QuickConfigUpdate {
  component_id: string;
  visible?: boolean;
  position?: Partial<ComponentConfig['position']>;
  size?: ComponentConfig['size'];
}

export interface BatchLayoutOperation {
  operation: 'activate' | 'delete' | 'copy';
  layout_ids: number[];
}

// ==================== API 服务 ====================

export const dashboardConfigService = {
  
  /**
   * 获取完整的仪表盘配置信息
   */
  async getConfig(): Promise<DashboardConfig> {
    const response = await api.get('/dashboard-config/');
    return response.data;
  },

  /**
   * 获取用户的布局列表
   */
  async listLayouts(page = 1, pageSize = 20): Promise<{
    total: number;
    items: DashboardLayout[];
  }> {
    const response = await api.get('/dashboard-config/layouts', {
      params: { page, page_size: pageSize }
    });
    return response.data;
  },

  /**
   * 创建新的布局
   */
  async createLayout(layout: Omit<DashboardLayout, 'id' | 'user_id' | 'created_at' | 'updated_at'>): Promise<DashboardLayout> {
    const response = await api.post('/dashboard-config/layouts', layout);
    return response.data;
  },

  /**
   * 更新布局
   */
  async updateLayout(layoutId: number, updates: Partial<DashboardLayout>): Promise<DashboardLayout> {
    const response = await api.put(`/dashboard-config/layouts/${layoutId}`, updates);
    return response.data;
  },

  /**
   * 删除布局
   */
  async deleteLayout(layoutId: number): Promise<void> {
    await api.delete(`/dashboard-config/layouts/${layoutId}`);
  },

  /**
   * 激活指定布局
   */
  async activateLayout(layoutId: number): Promise<void> {
    await api.post(`/dashboard-config/layouts/${layoutId}/activate`);
  },

  /**
   * 从预设模板创建布局
   */
  async createFromPreset(presetId: string, layoutName: string): Promise<DashboardLayout> {
    const response = await api.post('/dashboard-config/layouts/from-preset', {
      preset_id: presetId,
      layout_name: layoutName
    });
    return response.data;
  },

  /**
   * 快速更新组件配置（拖拽等实时操作）
   */
  async quickConfigUpdate(update: QuickConfigUpdate): Promise<void> {
    await api.post('/dashboard-config/quick-config', update);
  },

  /**
   * 获取可用组件列表
   */
  async getComponents(): Promise<DashboardComponent[]> {
    const response = await api.get('/dashboard-config/components');
    return response.data;
  },

  /**
   * 批量操作布局
   */
  async batchOperation(operation: BatchLayoutOperation): Promise<void> {
    await api.post('/dashboard-config/batch-operation', operation);
  },

  /**
   * 导出布局配置
   */
  async exportLayout(layoutId: number): Promise<string> {
    const response = await api.get(`/dashboard-config/layouts/${layoutId}/export`);
    return JSON.stringify(response.data, null, 2);
  },

  /**
   * 导入布局配置
   */
  async importLayout(layoutData: string, layoutName: string): Promise<DashboardLayout> {
    const config = JSON.parse(layoutData);
    return this.createLayout({
      name: layoutName,
      description: '从导入创建',
      is_active: false,
      is_preset: false,
      grid_cols: config.grid_cols || 24,
      config: config.config
    });
  }
};

// ==================== 本地存储 ====================

const STORAGE_PREFIX = 'nightmend_dashboard_';

export const localStorageService = {
  
  /**
   * 保存临时布局到本地存储（避免频繁API调用）
   */
  saveTempLayout(layout: DashboardLayout): void {
    localStorage.setItem(
      `${STORAGE_PREFIX}temp_layout`,
      JSON.stringify(layout)
    );
  },

  /**
   * 获取临时布局
   */
  getTempLayout(): DashboardLayout | null {
    const saved = localStorage.getItem(`${STORAGE_PREFIX}temp_layout`);
    return saved ? JSON.parse(saved) : null;
  },

  /**
   * 清除临时布局
   */
  clearTempLayout(): void {
    localStorage.removeItem(`${STORAGE_PREFIX}temp_layout`);
  },

  /**
   * 保存用户偏好设置
   */
  savePreferences(prefs: Record<string, any>): void {
    localStorage.setItem(
      `${STORAGE_PREFIX}preferences`,
      JSON.stringify(prefs)
    );
  },

  /**
   * 获取用户偏好设置
   */
  getPreferences(): Record<string, any> {
    const saved = localStorage.getItem(`${STORAGE_PREFIX}preferences`);
    return saved ? JSON.parse(saved) : {};
  }
};

// ==================== 布局工具函数 ====================

export const layoutUtils = {
  
  /**
   * 验证布局配置的合法性
   */
  validateLayout(layout: DashboardLayout): string[] {
    const errors: string[] = [];
    
    if (!layout.name || layout.name.trim().length === 0) {
      errors.push('布局名称不能为空');
    }
    
    if (layout.grid_cols < 12 || layout.grid_cols > 48) {
      errors.push('网格列数必须在12-48之间');
    }
    
    if (!layout.config || !layout.config.components) {
      errors.push('布局配置无效');
    } else {
      // 检查组件位置冲突
      const positions = new Set<string>();
      for (const component of layout.config.components) {
        if (component.visible) {
          const posKey = `${component.position.row}-${component.position.col}`;
          if (positions.has(posKey)) {
            errors.push(`组件 ${component.name} 的位置与其他组件冲突`);
          }
          positions.add(posKey);
        }
      }
    }
    
    return errors;
  },

  /**
   * 自动修复布局冲突
   */
  autoFixLayout(layout: DashboardLayout): DashboardLayout {
    const fixedLayout = { ...layout };
    const components = [...fixedLayout.config.components];
    
    // 按行排序组件，重新分配位置
    const visibleComponents = components.filter(c => c.visible);
    visibleComponents.sort((a, b) => {
      if (a.position.row !== b.position.row) {
        return a.position.row - b.position.row;
      }
      return a.position.col - b.position.col;
    });
    
    let currentRow = 0;
    let currentCol = 0;
    
    for (const component of visibleComponents) {
      // 如果当前行放不下，换到下一行
      if (currentCol + component.position.span > layout.grid_cols) {
        currentRow++;
        currentCol = 0;
      }
      
      component.position.row = currentRow;
      component.position.col = currentCol;
      
      currentCol += component.position.span;
    }
    
    fixedLayout.config.components = components;
    return fixedLayout;
  },

  /**
   * 计算布局的占用空间
   */
  calculateLayoutSize(layout: DashboardLayout): {
    totalRows: number;
    usedSpace: number;
    efficiency: number;
  } {
    const visibleComponents = layout.config.components.filter(c => c.visible);
    
    let maxRow = 0;
    let totalSpan = 0;
    
    for (const component of visibleComponents) {
      maxRow = Math.max(maxRow, component.position.row);
      totalSpan += component.position.span;
    }
    
    const totalRows = maxRow + 1;
    const totalSpace = totalRows * layout.grid_cols;
    const efficiency = totalSpace > 0 ? (totalSpan / totalSpace) * 100 : 0;
    
    return {
      totalRows,
      usedSpace: totalSpan,
      efficiency: Math.round(efficiency)
    };
  },

  /**
   * 生成默认布局
   */
  createDefaultLayout(components: DashboardComponent[]): DashboardLayout {
    const defaultComponents: ComponentConfig[] = components
      .filter(c => c.is_enabled)
      .sort((a, b) => a.sort_order - b.sort_order)
      .map((component, index) => ({
        id: component.id,
        name: component.name,
        visible: true,
        position: {
          row: Math.floor(index / 2), // 每行最多2个组件
          col: (index % 2) * 12,      // 左右分布
          span: 12
        }
      }));
    
    return {
      name: '默认布局',
      description: '系统生成的默认布局',
      is_active: false,
      is_preset: false,
      grid_cols: 24,
      config: {
        components: defaultComponents
      }
    };
  }
};