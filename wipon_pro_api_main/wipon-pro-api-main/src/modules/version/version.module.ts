import { Module } from '@nestjs/common';
import { VersionController } from './version.controller';
import { VersionService } from './domain/version.service';

@Module({
  providers: [VersionService],
  controllers: [VersionController],
})
export class VersionModule {}
