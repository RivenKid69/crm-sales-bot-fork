import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { DevicesRepository } from '../../data/devices.repository';
import { DeviceDao } from '../../../../common/dao/device.dao';

@Injectable()
export class FindUsersAllDevicesByAtUseCase {
  constructor(@InjectRepository(DevicesRepository) private readonly devicesRepository: DevicesRepository) {}
  handle(userId: number, applicationType: string): Promise<DeviceDao[]> {
    return this.devicesRepository.findUsersAllDevicesByApplicationType(userId, applicationType);
  }
}
