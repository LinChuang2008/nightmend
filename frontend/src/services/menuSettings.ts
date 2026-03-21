import api from './api';

export interface MenuSettingsPayload {
  hidden_keys: string[];
}

export const menuSettingsApi = {
  get: async (): Promise<MenuSettingsPayload> => {
    const { data } = await api.get<MenuSettingsPayload>('/menu-settings');
    return data;
  },
  update: async (payload: MenuSettingsPayload): Promise<MenuSettingsPayload> => {
    const { data } = await api.put<MenuSettingsPayload>('/menu-settings', payload);
    return data;
  },
};

