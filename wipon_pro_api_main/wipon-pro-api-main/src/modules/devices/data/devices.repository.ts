import { EntityRepository, MoreThan, Repository, UpdateResult } from 'typeorm';
import { DeviceDao } from '../../../common/dao/device.dao';

@EntityRepository(DeviceDao)
export class DevicesRepository extends Repository<DeviceDao> {
  async findUsersAllActiveDevices(userId: number): Promise<number> {
    const date = new Date();
    const yearAgo = new Date(date.setFullYear(date.getFullYear() - 1));
    return await this.count({ user_id: userId, updated_at: MoreThan(yearAgo) });
  }

  async findUsersDeviceByApplicationType(userId: number, applicationType: string): Promise<DeviceDao | undefined> {
    return await this.findOne({ user_id: userId, application_type: applicationType });
  }

  async findUsersAllDevicesByApplicationType(userId: number, applicationType: string): Promise<DeviceDao[]> {
    return await this.find({ user_id: userId, application_type: applicationType });
  }

  async findDeviceByApplicationTypeAndDeviceCode(applicationType: string, deviceCode: string) {
    const rawRes = await this.query(
      'select * from DEVICES where substring(device_code from 1 for 32) = $1 and application_type = $2 limit 1',
      [deviceCode, applicationType],
    );
    if (rawRes && Array.isArray(rawRes) && rawRes[0]) {
      return rawRes[0];
    }
    return undefined;
  }

  async assignDeviceToUser(userId: number, device: DeviceDao): Promise<UpdateResult> {
    return await this.update({ id: device.id }, { user_id: userId });
  }

  async checkUsersDevice(applicationType: string, userId: number): Promise<number> {
    return await this.count({ user_id: userId, application_type: applicationType });
  }
}
