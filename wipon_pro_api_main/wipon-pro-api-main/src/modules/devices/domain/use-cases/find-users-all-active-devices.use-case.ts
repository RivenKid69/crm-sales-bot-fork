import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { DevicesRepository } from '../../data/devices.repository';

@Injectable()
export class FindUsersAllActiveDevicesUseCase {
  constructor(@InjectRepository(DevicesRepository) private readonly devicesRepository: DevicesRepository) {}
  handle(userId: number): Promise<number> {
    return this.devicesRepository.findUsersAllActiveDevices(userId);
  }
}
