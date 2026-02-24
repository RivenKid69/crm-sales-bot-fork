import { HttpException, Injectable, NotFoundException } from '@nestjs/common';
import { AssignDeviceCodeDto } from '../dto/assign-device-code.dto';
import {
  // InjectEntityManager,
  InjectRepository,
} from '@nestjs/typeorm';
import { DevicesRepository } from '../data/devices.repository';
import { constants } from 'http2';
import { UserDao } from '../../../common/dao/user.dao';
import * as substr from 'locutus/php/strings/substr';
// import { EntityManager } from 'typeorm';
// import { DeviceDetailsEntity } from '../../../common/second-db-entities/device-details.entity';

@Injectable()
export class DevicesService {
  constructor(
    @InjectRepository(DevicesRepository) private readonly devicesRepository: DevicesRepository, // @InjectEntityManager('second-db') private secondDbEntityManager: EntityManager,
  ) {}

  // async test() {
  //   // return await this.secondDbEntityManager.findOne(DeviceDetailsEntity, 1);
  // }

  async assignDeviceCode(payload: AssignDeviceCodeDto, user: UserDao) {
    const deviceCode = payload.device_code.replace(/ctrlAlte|tab/gi, '');
    const formattedDeviceCode = deviceCode.length > 32 ? substr(deviceCode, 0, 32) : deviceCode;
    const device = await this.devicesRepository.findDeviceByApplicationTypeAndDeviceCode(
      payload.application_type,
      formattedDeviceCode,
    );
    if (!device) {
      throw new NotFoundException({ device_code: ['Device code not found'] });
    }

    if (device.user_id && device.user_id !== user.id) {
      throw new HttpException({ device_code: ['Device code is strange'] }, constants.HTTP_STATUS_UNPROCESSABLE_ENTITY);
    }

    if (!device.user_id) {
      await this.devicesRepository.assignDeviceToUser(user.id, device);
    }

    return { status: 'success' };
  }

  async checkUsersDevice(applicationType: string, userId: number) {
    let result = false;
    const count = await this.devicesRepository.checkUsersDevice(applicationType, userId);
    if (count) result = true;
    return { status: result };
  }
}
