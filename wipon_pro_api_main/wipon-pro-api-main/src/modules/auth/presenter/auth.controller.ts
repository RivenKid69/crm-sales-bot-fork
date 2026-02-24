import {
  Body,
  Controller,
  HttpCode,
  Post,
  UseInterceptors,
  UsePipes,
  ValidationPipe,
} from '@nestjs/common';
import { AuthService } from '../domain/auth.service';
import { LoginDto } from '../dto/login.dto';
import { TransformInterceptor } from '../../../common/interceptor/transform.interceptor';
import { ApiBody, ApiOkResponse, ApiOperation, ApiTags } from '@nestjs/swagger';

@Controller('auth')
@ApiTags('auth')
@UseInterceptors(TransformInterceptor)
export class AuthController {
  constructor(private readonly authService: AuthService) {}

  @Post()
  @HttpCode(200)
  @UsePipes(ValidationPipe)
  @ApiOperation({
    summary: 'Authentication',
  })
  @ApiOkResponse({
    schema: { type: 'object', example: { data: { status: 'success', resend_cooldown: 60, api_token: 'token' } } },
  })
  @ApiBody({ type: LoginDto })
  async auth(@Body() loginDto: LoginDto) {
    return await this.authService.login(loginDto);
  }
}
