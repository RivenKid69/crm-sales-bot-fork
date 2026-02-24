import { Module } from '@nestjs/common';
import { PdfController } from './pdf.controller';
import { UsersModule } from '../users/users.module';
import { PdfService } from './pdf.service';

@Module({
  providers: [PdfService],
  controllers: [PdfController],
  imports: [UsersModule],
})
export class PdfModule {}
