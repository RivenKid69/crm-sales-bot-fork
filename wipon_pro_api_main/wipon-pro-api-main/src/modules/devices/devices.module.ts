import { Module } from '@nestjs/common';
import { DevicesService } from './domain/devices.service';
import { DevicesController } from './presenter/devices.controller';
import { FindUsersDeviceByApplicationTypeUseCase } from './domain/use-cases/find-users-device-by-at';
import { TypeOrmModule } from '@nestjs/typeorm';
import { DevicesRepository } from './data/devices.repository';
import { UsersModule } from '../users/users.module';
import { FindUsersAllDevicesByAtUseCase } from './domain/use-cases/find-users-all-devices-by-at.use-case';
import { FindUsersAllActiveDevicesUseCase } from './domain/use-cases/find-users-all-active-devices.use-case';

@Module({
  imports: [TypeOrmModule.forFeature([DevicesRepository]), UsersModule],
  controllers: [DevicesController],
  providers: [
    DevicesService,
    FindUsersDeviceByApplicationTypeUseCase,
    FindUsersAllDevicesByAtUseCase,
    FindUsersAllActiveDevicesUseCase,
  ],
  exports: [FindUsersDeviceByApplicationTypeUseCase, FindUsersAllDevicesByAtUseCase, FindUsersAllActiveDevicesUseCase],
})
export class DevicesModule {}
