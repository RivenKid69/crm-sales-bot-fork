import { Body, Controller, Header, Post, Res, UseGuards } from '@nestjs/common';
import { Response } from 'express';
import { AuthGuard } from '../auth/guard/auth.guard';
import { User } from '../../common/decorators/user.decorator';
import { UserDao } from '../../common/dao/user.dao';
import { GenerateInvoiceDto } from './dto/generate-invoice.dto';
import { PdfService } from './pdf.service';

@Controller('pdf')
export class PdfController {
  constructor(private readonly pdfService: PdfService) {}

  @Post('invoice')
  @UseGuards(AuthGuard)
  @Header('Content-Type', 'application/pdf')
  @Header('Content-Disposition', 'inline; filename=file.pdf')
  async generateInvoice(
    @User() user: UserDao,
    @Body() generateInvoiceDto: GenerateInvoiceDto,
    @Res() response: Response,
  ) {
    return await this.pdfService.generateInvoice(user, generateInvoiceDto, response);
  }
}
